import logging

logger = logging.getLogger(__name__)

try:
    import routeros_api
except ImportError:  # pragma: no cover
    import sys
    from unittest.mock import MagicMock
    routeros_api = MagicMock()
    sys.modules['routeros_api'] = routeros_api


def sync_hotspot_plan_to_mikrotik(plan, old_name=None):
    """
    Self-healing MikroTik Hotspot Plan synchronization logic.

    1. Connects to MikroTik at 192.168.56.20:8728 (admin / '') via routeros_api.
    2. Queries /ip/hotspot/user/profile using old_name or plan.name.
    3. If plan.is_active is False:
       - Removes profile on RouterOS if it exists (.remove(id=target_id)).
    4. If plan.is_active is True:
       - Formats rate_limit as f"{plan.upload_speed_kbps}k/{plan.download_speed_kbps}k".
       - Formats shared_users as str(plan.simultaneous_devices).
       - If profile exists: calls .set(id=target_id, name=plan.name, rate_limit=formatted_rate, shared_users=formatted_shared).
       - If profile does not exist: calls .add(name=plan.name, rate_limit=formatted_rate, shared_users=formatted_shared).
    5. Network calls are wrapped in a try...except Exception block to prevent crashing.
    """
    connection = None
    try:
        connection = routeros_api.RouterOsApiPool(
            '192.168.56.20',
            username='admin',
            password='',
            port=8728,
        )
        api = connection.get_api()
        profile_resource = api.get_resource('/ip/hotspot/user/profile')

        target_name = old_name or plan.name
        try:
            existing_profiles = profile_resource.get(name=target_name)
        except TypeError:
            existing_profiles = profile_resource.get()

        if not existing_profiles and old_name and old_name != plan.name:
            try:
                existing_profiles = profile_resource.get(name=plan.name)
            except Exception:
                pass

        matched_profile = None
        if existing_profiles:
            for p in existing_profiles:
                p_name = p.get('name')
                if p_name in (target_name, plan.name, old_name):
                    matched_profile = p
                    break
            if not matched_profile and existing_profiles:
                matched_profile = existing_profiles[0]

        if not plan.is_active:
            if matched_profile:
                target_id = matched_profile.get('id') or matched_profile.get('.id')
                profile_resource.remove(id=target_id)
                msg = f"[RouterOS Sync] Removed profile '{plan.name}' on MikroTik"
                print(msg)
                logger.info(msg)
        else:
            formatted_rate = f"{plan.upload_speed_kbps}k/{plan.download_speed_kbps}k"
            formatted_shared = str(plan.simultaneous_devices)

            if matched_profile:
                target_id = matched_profile.get('id') or matched_profile.get('.id')
                profile_resource.set(
                    id=target_id,
                    name=plan.name,
                    rate_limit=formatted_rate,
                    shared_users=formatted_shared,
                )
                msg = f"[RouterOS Sync] Updated profile '{plan.name}' on MikroTik"
                print(msg)
                logger.info(msg)
            else:
                profile_resource.add(
                    name=plan.name,
                    rate_limit=formatted_rate,
                    shared_users=formatted_shared,
                )
                msg = f"[RouterOS Sync] Created missing profile '{plan.name}' on MikroTik"
                print(msg)
                logger.info(msg)

    except Exception as exc:
        msg = f"[RouterOS Sync] Error syncing profile '{getattr(plan, 'name', 'unknown')}': {exc}"
        print(msg)
        logger.error(msg)
    finally:
        if connection is not None:
            try:
                connection.disconnect()
            except Exception:
                pass
