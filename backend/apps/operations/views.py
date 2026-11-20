import logging

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import OperationalError
from django.db.models import OuterRef, Q, Subquery
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.radius.models import RadAcct
from apps.routers.models import NAS
from apps.tenants.models import Tenant
from apps.vouchers.models import Recharge
from core.permissions import (
    IsCustomer, IsSuperAdminOnly, IsSuperAdminOrVendor, IsVendorCashier,
    IsVendorManager, IsVendorPlanViewer, IsVendorTechnician, tenant_for_user,
)
from .models import Customer, Invoice, PlatformSettings, PlatformUser, SupportTicket, TicketMessage
from .serializers import (
    CustomerSerializer, InvoiceSerializer, PlatformSettingsSerializer,
    PlatformUserSerializer, SupportTicketSerializer, TicketMessageSerializer,
)

logger = logging.getLogger(__name__)


class TenantScopedViewSet(viewsets.ModelViewSet):
    permission_classes = [IsSuperAdminOrVendor]

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.request.user.is_superadmin:
            tenant_id = self.request.query_params.get('tenant_id')
            return queryset.filter(tenant_id=tenant_id) if tenant_id else queryset
        tenant = tenant_for_user(self.request.user)
        return queryset.filter(tenant_id=tenant.id) if tenant else queryset.none()


class CustomerViewSet(TenantScopedViewSet):
    queryset = Customer.objects.select_related('tenant').all()
    serializer_class = CustomerSerializer

    def get_permissions(self):
        if getattr(self.request.user, 'customer_profile', None):
            if self.action in ('list', 'retrieve'):
                return [IsCustomer()]
            return [IsSuperAdminOrVendor()]
        if self.action in ('list', 'retrieve'):
            return [IsSuperAdminOrVendor()]
        return [IsVendorManager()]

    def get_queryset(self):
        customer = getattr(self.request.user, 'customer_profile', None)
        if customer:
            queryset = self.queryset.filter(user=self.request.user)
        else:
            queryset = super().get_queryset()

        now = timezone.now()
        active_recharges = Recharge.objects.filter(
            tenant_id=OuterRef('tenant_id'),
            username=OuterRef('username'),
            expires_at__gt=now,
        ).order_by('-expires_at')
        pending_ids = (
            queryset.filter(status__iexact='pending')
            .annotate(active_expiry=Subquery(active_recharges.values('expires_at')[:1]))
            .filter(active_expiry__gt=now)
            .values('pk')
        )
        Customer.objects.filter(pk__in=pending_ids).update(
            status=Customer.Status.ACTIVE,
            expires_at=Subquery(active_recharges.values('expires_at')[:1]),
        )
        queryset.filter(expires_at__lte=now).exclude(
            status__iexact=Customer.Status.BLOCKED,
        ).exclude(
            status__iexact=Customer.Status.EXPIRED,
        ).update(status=Customer.Status.EXPIRED)
        return queryset


class InvoiceViewSet(TenantScopedViewSet):
    queryset = Invoice.objects.select_related('tenant').all()
    serializer_class = InvoiceSerializer

    def get_permissions(self):
        if getattr(self.request.user, 'customer_profile', None):
            if self.action in ('list', 'retrieve'):
                return [IsCustomer()]
            return [IsSuperAdminOrVendor()]
        if self.action in ('list', 'retrieve', 'create'):
            return [IsVendorCashier()]
        return [IsVendorManager()]

    def get_queryset(self):
        customer = getattr(self.request.user, 'customer_profile', None)
        if customer:
            return self.queryset.filter(tenant_id=customer.tenant_id, customer_phone=customer.phone_number)
        return super().get_queryset()


class SupportTicketViewSet(TenantScopedViewSet):
    queryset = SupportTicket.objects.select_related('tenant').prefetch_related('messages').all()
    serializer_class = SupportTicketSerializer

    def get_permissions(self):
        if getattr(self.request.user, 'customer_profile', None):
            if self.action in ('list', 'retrieve', 'create', 'add_message'):
                return [IsCustomer()]
            return [IsSuperAdminOrVendor()]
        if self.action in ('list', 'retrieve'):
            return [IsVendorPlanViewer()]
        if self.action == 'destroy':
            return [IsVendorManager()]
        if self.action in ('create', 'update', 'partial_update', 'add_message'):
            return [IsVendorTechnician()]
        return [IsVendorManager()]

    def get_queryset(self):
        customer = getattr(self.request.user, 'customer_profile', None)
        if customer:
            return self.queryset.filter(tenant_id=customer.tenant_id, customer_phone=customer.phone_number)
        return super().get_queryset()

    @action(detail=True, methods=['post'], url_path='messages')
    def add_message(self, request, pk=None):
        ticket = self.get_object()
        text = str(request.data.get('text', '')).strip()
        if not text:
            return Response({'detail': 'Message text is required.'}, status=status.HTTP_400_BAD_REQUEST)
        is_staff = not bool(getattr(request.user, 'customer_profile', None))
        message = TicketMessage.objects.create(
            ticket=ticket,
            sender=request.user.get_full_name() or request.user.username,
            is_staff=is_staff,
            text=text,
        )
        ticket.save(update_fields=['updated_at'])
        return Response(TicketMessageSerializer(message).data, status=status.HTTP_201_CREATED)


class SystemUserViewSet(viewsets.ModelViewSet):
    queryset = PlatformUser.objects.select_related('user').all().order_by('user__username')
    serializer_class = PlatformUserSerializer
    permission_classes = [IsSuperAdminOnly]
    http_method_names = ['get', 'post', 'patch', 'delete', 'head', 'options']

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.user.is_active = False
        instance.user.save(update_fields=['is_active'])
        return Response(status=status.HTTP_204_NO_CONTENT)


class PlatformSettingsView(APIView):
    permission_classes = [IsSuperAdminOnly]

    def get(self, request):
        settings_record, _ = PlatformSettings.objects.get_or_create(pk=1)
        return Response(PlatformSettingsSerializer(settings_record).data)

    def patch(self, request):
        settings_record, _ = PlatformSettings.objects.get_or_create(pk=1)
        serializer = PlatformSettingsSerializer(settings_record, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class ActiveSessionListView(APIView):
    permission_classes = [IsSuperAdminOrVendor]

    def get_permissions(self):
        if getattr(self.request.user, 'customer_profile', None):
            return [IsCustomer()]
        return [IsVendorPlanViewer()]

    def get(self, request):
        return self.get_sessions(request, active_only=True)

    def get_sessions(self, request, *, active_only):
        customer = getattr(request.user, 'customer_profile', None)
        if request.user.is_superadmin:
            tenant_id = request.query_params.get('tenant_id')
            routers = NAS.objects.filter(tenant_id=tenant_id) if tenant_id else NAS.objects.all()
        elif customer:
            routers = NAS.objects.filter(tenant_id=customer.tenant_id)
        else:
            tenant = tenant_for_user(request.user)
            routers = NAS.objects.filter(tenant_id=tenant.id) if tenant else NAS.objects.none()

        router_by_ip = {
            router.nas_ip: router
            for router in routers
        }
        try:
            now = timezone.now()
            tenant_ids = {router.tenant_id for router in router_by_ip.values()}
            expired_identities = set()
            if active_only and tenant_ids:
                expired_customers = Customer.objects.filter(
                    tenant_id__in=tenant_ids,
                ).filter(
                    Q(status__iexact=Customer.Status.EXPIRED)
                    | Q(expires_at__lte=now)
                ).values_list('tenant_id', 'username', 'phone_number', 'mac_address')
                for tenant_id, username, phone_number, mac_address in expired_customers:
                    for identity in (username, phone_number, mac_address):
                        if identity:
                            expired_identities.add((str(tenant_id), identity.strip().casefold()))

            rows = RadAcct.objects.using('radius_db').filter(nasipaddress__in=list(router_by_ip))
            rows = rows.filter(acctstoptime__isnull=True) if active_only else rows.filter(acctstoptime__isnull=False)
            rows = rows.order_by('-acctstarttime')
            if customer:
                rows = rows.filter(Q(username=customer.username) | Q(callingstationid__iexact=customer.mac_address))
            sessions = []
            for row in rows:
                router = router_by_ip.get(str(row.nasipaddress))
                if router is None:
                    continue
                session_identities = {
                    identity.strip().casefold()
                    for identity in (row.username, row.callingstationid)
                    if identity
                }
                if any(
                    (str(router.tenant_id), identity) in expired_identities
                    for identity in session_identities
                ):
                    continue
                sessions.append({
                    'id': str(row.radacctid),
                    'tenant_id': str(router.tenant_id),
                    'username': row.username,
                    'ip_address': str(row.framedipaddress or ''),
                    'mac_address': row.callingstationid,
                    'service_type': 'pppoe' if (row.servicetype or '').lower() == 'framed' else 'hotspot',
                    'uptime_seconds': row.acctsessiontime or 0,
                    'rx_bytes': row.acctinputoctets or 0,
                    'tx_bytes': row.acctoutputoctets or 0,
                    'started_at': row.acctstarttime,
                    'router_name': router.shortname or router.nasname,
                    'stopped_at': row.acctstoptime,
                    'terminate_cause': row.acctterminatecause,
                })
        except OperationalError as exc:
            logger.warning(
                'RADIUS accounting data is unavailable; returning no sessions (active_only=%s): %s',
                active_only,
                exc,
            )
            sessions = []
        except Exception:
            logger.exception(
                'Unable to load RADIUS accounting sessions; returning no sessions (active_only=%s).',
                active_only,
            )
            sessions = []
        return Response(sessions)


class SessionHistoryView(ActiveSessionListView):
    def get(self, request):
        return self.get_sessions(request, active_only=False)


class ActiveSessionDisconnectView(APIView):
    permission_classes = [IsVendorTechnician]

    def post(self, request, session_id):
        row = get_object_or_404(
            RadAcct.objects.using('radius_db').filter(acctstoptime__isnull=True),
            radacctid=session_id,
        )
        if request.user.is_superadmin:
            routers = NAS.objects.filter(nas_ip=str(row.nasipaddress))
        else:
            tenant = tenant_for_user(request.user)
            routers = NAS.objects.filter(tenant=tenant, nas_ip=str(row.nasipaddress)) if tenant else NAS.objects.none()
        router = routers.first()
        if not router:
            return Response({'detail': 'No router binding exists for this live session.'}, status=status.HTTP_404_NOT_FOUND)

        try:
            from routeros_api import RouterOsApiPool
            from apps.routers.services import resolve_router_credentials

            username, password = resolve_router_credentials(router)
            if not username or not password:
                return Response({'detail': 'Router API credentials are not configured.'}, status=status.HTTP_409_CONFLICT)
            pool = RouterOsApiPool(
                router.nas_ip or router.nasname,
                username=username,
                password=password,
                port=router.api_port,
                plaintext_login=True,
                use_ssl=False,
                ssl_verify=False,
                ssl_verify_hostname=False,
                socket_timeout=3.0,
            )
            try:
                api = pool.get_api()
                resource_path = '/ppp/active' if (row.servicetype or '').lower() == 'framed' else '/ip/hotspot/active'
                resource = api.get_resource(resource_path)
                active_entries = resource.get(name=row.username)
                if not active_entries:
                    return Response({'detail': 'The session is no longer active on the router.'}, status=status.HTTP_404_NOT_FOUND)
                for entry in active_entries:
                    resource.remove(id=entry['.id'])
            finally:
                pool.disconnect()
        except ImportError:
            return Response({'detail': 'RouterOS API package is not installed on the server.'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        except Exception:
            logger.exception('Unable to disconnect session %s through router %s', session_id, router.pk)
            return Response({'detail': 'Router session disconnect failed. Check router connectivity and credentials.'}, status=status.HTTP_502_BAD_GATEWAY)

        return Response({'success': True, 'message': f'Session for {row.username} disconnected.'})


class CustomerProfileView(APIView):
    permission_classes = [IsCustomer]

    def get(self, request):
        customer = getattr(request.user, 'customer_profile', None)
        if not customer:
            return Response({'detail': 'Customer profile not found.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(CustomerSerializer(customer).data)


class CustomerPasswordView(APIView):
    permission_classes = [IsCustomer]

    def post(self, request):
        if not getattr(request.user, 'customer_profile', None):
            return Response({'detail': 'A customer account is required.'}, status=status.HTTP_403_FORBIDDEN)
        old_password = str(request.data.get('current_password', ''))
        new_password = str(request.data.get('new_password', ''))
        if not request.user.check_password(old_password):
            return Response({'current_password': ['Current password is incorrect.']}, status=status.HTTP_400_BAD_REQUEST)
        try:
            validate_password(new_password, request.user)
        except ValidationError as exc:
            return Response({'new_password': exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        request.user.set_password(new_password)
        request.user.save(update_fields=['password'])
        return Response({'success': True})
