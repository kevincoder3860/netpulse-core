import ipaddress
import logging
import socket as _socket
from decimal import Decimal
from datetime import timedelta
from django.db import transaction
from django.db.models import Q
from django.utils.dateparse import parse_datetime
from django.utils import timezone
from apps.billing.models import Transaction
from apps.radius.models import RadCheck, RadReply

logger = logging.getLogger(__name__)


def get_routeros_timeout(value, unit):
    normalized_unit = str(unit).lower()
    if normalized_unit in ('minute', 'minutes', 'min', 'm'):
        suffix = 'm'
    elif normalized_unit in ('hour', 'hours', 'hr', 'h'):
        suffix = 'h'
    elif normalized_unit in ('day', 'days', 'd'):
        suffix = 'd'
    else:
        suffix = 'h'
    return f'{value}{suffix}'


def format_routeros_time(minutes: int) -> str:
    """Format minutes into RouterOS time format e.g., 1d02:30:00 or 02:30:00"""
    days = minutes // 1440
    hours = (minutes % 1440) // 60
    mins = minutes % 60
    if days > 0:
        return f"{days}d{hours:02d}:{mins:02d}:00"
    return f"{hours:02d}:{mins:02d}:00"


def sync_hotspot_plan_profile_to_routers(plan, action='create', old_name=None):
    """
    Syncs a Django HotspotPlan to /ip/hotspot/user/profile on all online MikroTik routers
    belonging to the plan's tenant.

    action: 'create' | 'update' | 'delete'

    Self-healing behaviour
    ----------------------
    - create/update + profile EXISTS   → .set() updates the existing entry
    - create/update + profile MISSING  → .add() re-creates it (handles WinBox manual deletions)
    - update + is_active=False         → .remove() deactivates the profile on the device
    - delete                           → .remove() all matching entries
    """
    from apps.routers.models import NAS

    name_to_search = old_name or plan.name
    new_name = plan.name
    rate_limit = f"{plan.upload_speed_kbps}k/{plan.download_speed_kbps}k"
    shared_users = str(plan.simultaneous_devices)
    session_timeout = get_routeros_timeout(plan.duration_value, plan.duration_unit)

    for router in NAS.objects.filter(tenant=plan.tenant, is_online=True, type='mikrotik'):
        connection = None
        try:
            from librouteros import connect
            from librouteros.query import Key

            # Enforce a 5-second connect timeout so the call never blocks indefinitely
            _prev_timeout = _socket.getdefaulttimeout()
            _socket.setdefaulttimeout(5)
            try:
                connection = connect(
                    host=router.nas_ip,
                    username=router.api_username,
                    password=router.api_password,
                    port=router.api_port or 8728,
                )
            finally:
                _socket.setdefaulttimeout(_prev_timeout)

            profile_path = connection.path('/ip/hotspot/user/profile')

            # ── DELETE action ────────────────────────────────────────────────
            if action == 'delete':
                existing = list(profile_path.select('.id').where(Key('name') == name_to_search))
                for p in existing:
                    profile_path.remove(p['.id'])
                msg = f"[RouterOS Sync] Deleted profile '{name_to_search}' on {router.nas_ip}"
                print(msg)
                logger.info(msg)
                continue  # next router

            # ── Deactivate: is_active toggled to False ───────────────────────
            if action == 'update' and not plan.is_active:
                existing = list(profile_path.select('.id').where(Key('name') == name_to_search))
                if not existing and name_to_search != new_name:
                    existing = list(profile_path.select('.id').where(Key('name') == new_name))
                for p in existing:
                    profile_path.remove(p['.id'])
                msg = f"[RouterOS Sync] Deactivated (removed) profile '{new_name}' on {router.nas_ip}"
                print(msg)
                logger.info(msg)
                continue  # next router

            # ── CREATE / UPDATE / Re-activate ────────────────────────────────
            # Search by old_name first (covers rename), then fall back to new_name
            existing = list(profile_path.select('.id').where(Key('name') == name_to_search))
            if not existing and name_to_search != new_name:
                existing = list(profile_path.select('.id').where(Key('name') == new_name))

            if existing:
                # Profile found on MikroTik — update it in-place
                target_id = existing[0]['.id']
                profile_path.set(**{
                    '.id': target_id,
                    'name': new_name,
                    'rate-limit': rate_limit,
                    'shared-users': shared_users,
                    'session-timeout': session_timeout,
                })
                msg = f"[RouterOS Sync] Updated profile '{new_name}' on MikroTik"
                print(msg)
                logger.info(msg)
            else:
                # Profile missing from MikroTik (e.g. manually cleared in WinBox) — recreate it
                profile_path.add(**{
                    'name': new_name,
                    'rate-limit': rate_limit,
                    'shared-users': shared_users,
                    'session-timeout': session_timeout,
                })
                msg = f"[RouterOS Sync] Created missing profile '{new_name}' on MikroTik"
                print(msg)
                logger.info(msg)

        except _socket.timeout:
            msg = (
                f"[RouterOS Sync] Connection timed out for router {router.nas_ip}"
                f" — profile '{new_name}' not synced"
            )
            print(msg)
            logger.warning(msg)
        except Exception as exc:
            msg = f"[RouterOS Sync] Error syncing profile '{new_name}' to {router.nas_ip}: {exc}"
            print(msg)
            logger.error(msg)
        finally:
            if connection is not None:
                try:
                    connection.close()
                except Exception:
                    pass




def _payment_time_from_provider(provider_data):
    value = provider_data.get('paid_at') or provider_data.get('transaction_date')
    if not isinstance(value, str):
        return None
    paid_at = parse_datetime(value)
    if paid_at and timezone.is_naive(paid_at):
        paid_at = timezone.make_aware(paid_at)
    return paid_at


def _validate_paystack_payment(txn, provider_data):
    if txn.payment_method != 'PAYSTACK_MOBILE_MONEY':
        return
    try:
        received_amount = int(provider_data['amount'])
    except (KeyError, TypeError, ValueError):
        raise ValueError('Verified Paystack payment is missing a valid amount.') from None

    expected_amount = int(txn.gross_amount * 100)
    if (
        provider_data.get('reference') != txn.checkout_request_id
        or str(provider_data.get('status', '')).lower() != 'success'
        or str(provider_data.get('currency', '')).upper() != 'KES'
        or received_amount != expected_amount
    ):
        raise ValueError('Verified Paystack payment does not match the transaction.')


def _sync_paid_user_to_router(router, plan, username, mac_address=''):
    if router is None:
        logger.warning('No bound MikroTik router is available for hotspot user provisioning.')
        return
    if router.type != 'mikrotik':
        logger.info('Skipping RouterOS hotspot provisioning for non-MikroTik NAS %s', router.pk)
        return

    connection = None
    configured_hosts = [
        str(value).strip()
        for value in (router.nas_ip, router.nasname)
        if value and str(value).strip()
    ]
    host = ''
    configured_host = configured_hosts[0] if configured_hosts else ''
    port = router.api_port or 8728
    stage = 'validate router API address'
    try:
        from librouteros import connect
        from librouteros.query import Key
        from apps.routers.services import resolve_router_credentials

        for candidate in configured_hosts:
            try:
                address = ipaddress.ip_address(candidate)
            except ValueError:
                continue
            if address.version == 4:
                host = str(address)
                break
        if not host:
            raise ValueError(
                'No valid IPv4 RouterOS API address is configured; set the router management IP '
                f'to a reachable IPv4 address (configured values: {", ".join(configured_hosts) or "none"}).'
            )
        port = int(port)
        api_username, api_password = resolve_router_credentials(router)
        if not host or not api_username or not api_password:
            raise ValueError('Router API host and credentials must be configured.')
        if not router.is_online:
            logger.info(
                'NAS %s is marked offline; attempting a bounded RouterOS provisioning connection.',
                router.pk,
            )
        stage = 'connect to RouterOS API'
        logger.info(
            'Connecting to RouterOS API for hotspot provisioning on NAS %s at %s:%s.',
            router.pk,
            host,
            port,
        )
        connection = connect(
            host=host,
            username=api_username,
            password=api_password,
            port=port,
            timeout=5,
        )

        stage = 'sync hotspot user profile'
        profile_path = connection.path('/ip/hotspot/user/profile')
        existing_profiles = list(profile_path.select('.id').where(Key('name') == plan.name))
        profile_params = {
            'rate-limit': f'{plan.upload_speed_kbps or 0}k/{plan.download_speed_kbps or 0}k',
            'shared-users': str(plan.simultaneous_devices),
            'session-timeout': format_routeros_time(plan.duration_minutes),
        }
        if existing_profiles:
            profile_path.set(**{
                '.id': existing_profiles[0]['.id'],
                'name': plan.name,
                **profile_params,
            })
        else:
            profile_path.add(name=plan.name, **profile_params)

        stage = 'find hotspot user'
        user_path = connection.path('/ip/hotspot/user')
        existing_user = list(user_path.select('.id').where(Key('name') == username))
        user_params = {
            'password': username,
            'profile': plan.name,
            'limit-uptime': plan.limit_uptime,
        }
        mac_parts = str(mac_address or '').strip().upper().split(':')
        if len(mac_parts) == 6 and all(
            len(part) == 2 and all(character in '0123456789ABCDEF' for character in part)
            for part in mac_parts
        ):
            user_params['mac-address'] = ':'.join(mac_parts)
        if existing_user:
            stage = 'update hotspot user'
            user_path.set(**{
                '.id': existing_user[0]['.id'],
                'name': username,
                **user_params,
            })
            action = 'updated'
        else:
            stage = 'create hotspot user'
            user_path.add(name=username, **user_params)
            action = 'created'
        logger.info(
            'RouterOS Hotspot -> Users user %s was %s on NAS %s at %s:%s with profile %s.',
            username,
            action,
            router.pk,
            host,
            port,
            plan.name,
        )
    except Exception as exc:
        logger.warning(
            'RouterOS hotspot provisioning failed during %s for NAS %s at %s:%s: %s; '
            'payment and RADIUS provisioning remain recorded.',
            stage,
            router.pk,
            host or configured_host,
            port,
            exc,
            exc_info=True,
        )
    finally:
        if connection is not None:
            try:
                connection.close()
            except Exception:
                logger.warning('Failed to close RouterOS connection for NAS %s', router.pk)


def process_successful_payment(transaction_id: str, *, provider_data=None):
    """Idempotently record payment, entitlement, RADIUS credentials, and router user."""
    from apps.operations.models import Customer
    from apps.routers.models import NAS
    from apps.vouchers.models import Recharge

    with transaction.atomic():
        txn = (
            Transaction.objects.select_for_update()
            .select_related('tenant', 'plan', 'nas')
            .get(id=transaction_id)
        )
        plan = txn.plan
        if plan is None:
            raise ValueError('Cannot provision a paid transaction without a hotspot plan.')
        if plan.tenant_id != txn.tenant_id:
            raise ValueError('Cannot provision a transaction with a plan from another tenant.')
        router = txn.nas
        router_assignment_changed = False
        if router and router.tenant_id != txn.tenant_id:
            logger.error(
                'Ignoring NAS %s on transaction %s because it belongs to tenant %s, not payment tenant %s.',
                router.pk,
                txn.pk,
                router.tenant_id,
                txn.tenant_id,
            )
            router = None
            router_assignment_changed = True
        if router is None:
            router = (
                NAS.objects.filter(tenant_id=txn.tenant_id, type='mikrotik')
                .order_by('-is_online', '-last_seen', 'id')
                .first()
            )
            if txn.nas_id != (router.pk if router else None):
                txn.nas = router
                router_assignment_changed = True

        if provider_data is not None:
            _validate_paystack_payment(txn, provider_data)

        username = (txn.client_mac or txn.phone_number or '').strip()
        if not username:
            raise ValueError('Cannot provision a paid transaction without a username or phone number.')
        hotspot_username = (txn.phone_number or '').strip()
        if not hotspot_username and txn.payment_method == 'VOUCHER':
            hotspot_username = username
        if not hotspot_username:
            raise ValueError(
                'Cannot provision a paid hotspot user without the customer phone number.'
            )

        previous_status = txn.status
        now = timezone.now()
        paid_at = (
            txn.paid_at
            or (_payment_time_from_provider(provider_data) if provider_data else None)
            or (txn.updated_at if previous_status == 'COMPLETED' else now)
        )
        gateway_receipt = txn.gateway_receipt
        gateway_fee = txn.gateway_fee
        if provider_data:
            receipt = (
                provider_data.get('receipt')
                or provider_data.get('receipt_number')
                or provider_data.get('mpesa_receipt_number')
            )
            if receipt is not None and str(receipt):
                gateway_receipt = str(receipt)[:128]
            provider_fee = provider_data.get('fees')
            if provider_fee is not None:
                try:
                    gateway_fee = (Decimal(str(provider_fee)) / Decimal('100')).quantize(Decimal('0.01'))
                    if gateway_fee < 0:
                        raise ValueError
                except (ArithmeticError, TypeError, ValueError):
                    logger.warning('Ignoring invalid Paystack fee for transaction %s', txn.pk)

        identity = Q(username=username)
        if txn.client_mac:
            identity |= Q(mac_address__iexact=txn.client_mac)
        if txn.phone_number:
            identity |= Q(phone_number=txn.phone_number)
        customer = (
            Customer.objects.select_for_update()
            .filter(tenant_id=txn.tenant_id)
            .filter(identity)
            .order_by('-created_at')
            .first()
        )

        recharge = Recharge.objects.select_for_update().filter(transaction=txn).first()
        if recharge and recharge.expires_at:
            entitlement_expires_at = recharge.expires_at
        elif previous_status == 'COMPLETED':
            entitlement_expires_at = (
                customer.expires_at
                if customer and customer.expires_at
                else paid_at + timedelta(minutes=plan.duration_minutes)
            )
        else:
            start_at = paid_at
            if customer and customer.expires_at and customer.expires_at > start_at:
                start_at = customer.expires_at
            entitlement_expires_at = start_at + timedelta(minutes=plan.duration_minutes)

        if customer is None:
            customer = Customer(
                tenant=txn.tenant,
                username=username,
                name=txn.phone_number or username,
                phone_number=txn.phone_number or '',
                mac_address=txn.client_mac or '',
            )
        customer.plan_name = plan.name
        customer.service_type = Customer.ServiceType.HOTSPOT
        customer.expires_at = max(
            (customer.expires_at, entitlement_expires_at)
            if customer.expires_at else (entitlement_expires_at,)
        )
        customer.status = (
            Customer.Status.ACTIVE
            if customer.expires_at > timezone.now()
            else Customer.Status.EXPIRED
        )
        if txn.phone_number:
            customer.phone_number = txn.phone_number
        if txn.client_mac:
            customer.mac_address = txn.client_mac
        customer.save()

        recharge_defaults = {
            'tenant': txn.tenant,
            'username': username,
            'mac_address': txn.client_mac or '',
            'plan': plan,
            'router': router,
            'method': 'VOUCHER' if txn.payment_method == 'VOUCHER' else 'SYSTEM',
            'expires_at': entitlement_expires_at,
        }
        if recharge is None:
            Recharge.objects.create(transaction=txn, **recharge_defaults)
        else:
            for field, value in recharge_defaults.items():
                setattr(recharge, field, value)
            recharge.save(update_fields=list(recharge_defaults))

        txn.status = 'COMPLETED'
        txn.paid_at = paid_at
        txn.gateway_receipt = gateway_receipt
        txn.gateway_fee = gateway_fee
        update_fields = ['status', 'paid_at', 'gateway_receipt', 'gateway_fee', 'updated_at']
        if router_assignment_changed:
            update_fields.append('nas')
        txn.save(update_fields=update_fields)

        # RADIUS uses a separate database; commit its paired upserts atomically and last.
        with transaction.atomic(using='radius_db'):
            RadCheck.objects.using('radius_db').update_or_create(
                username=username,
                attribute='Cleartext-Password',
                defaults={'op': ':=', 'value': username},
            )
            RadReply.objects.using('radius_db').update_or_create(
                username=username,
                attribute='Session-Timeout',
                defaults={'op': ':=', 'value': str(plan.duration_minutes * 60)},
            )
            if plan.download_speed_kbps or plan.upload_speed_kbps:
                rate_limit = f'{plan.upload_speed_kbps or 0}k/{plan.download_speed_kbps or 0}k'
                RadReply.objects.using('radius_db').update_or_create(
                    username=username,
                    attribute='Mikrotik-Rate-Limit',
                    defaults={'op': ':=', 'value': rate_limit},
                )

    _sync_paid_user_to_router(
        router,
        plan,
        hotspot_username,
        txn.client_mac,
    )
    return txn
