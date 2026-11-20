from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import SAFE_METHODS
import logging
import socket

from django.utils import timezone
from django.db import OperationalError

from .models import NAS
from .serializers import NASSerializer
from core.permissions import (
    HasStaffPermission, IsCustomer, IsSuperAdminOrVendor, IsVendorManager,
    is_superadmin_user, tenant_for_user,
)
from .services import (
    RouterConnectionError, fetch_router_metrics, update_router_health,
)

logger = logging.getLogger(__name__)

def _database_error_response(exc, *, operation):
    is_busy = 'locked' in str(exc).lower() or 'busy' in str(exc).lower()
    code = 'DATABASE_BUSY' if is_busy else 'DATABASE_UNAVAILABLE'
    detail = (
        'Router data is temporarily unavailable because the database is busy.'
        if is_busy
        else 'Router data is temporarily unavailable.'
    )
    logger.warning('Router %s failed with %s: %s', operation, code, exc)
    return Response(
        {'detail': detail, 'code': code},
        status=status.HTTP_503_SERVICE_UNAVAILABLE,
    )


class RouterViewSet(viewsets.ModelViewSet):
    queryset = NAS.objects.all()
    serializer_class = NASSerializer
    permission_classes = [IsSuperAdminOrVendor]

    def get_permissions(self):
        if self.request.method in SAFE_METHODS:
            if getattr(self.request.user, 'customer_profile', None):
                return [IsCustomer()]
            return [HasStaffPermission('MANAGER', 'TECHNICIAN', 'CASHIER')]
        return [IsVendorManager()]

    def get_queryset(self):
        queryset = super().get_queryset()
        tenant_id = self.request.query_params.get('tenant_id')
        if is_superadmin_user(self.request.user):
            return queryset.filter(tenant_id=tenant_id) if tenant_id else queryset
        tenant = tenant_for_user(self.request.user)
        if tenant:
            return queryset.filter(tenant_id=tenant.id)
        return queryset.none()

    def perform_create(self, serializer):
        tenant = tenant_for_user(self.request.user)
        if tenant:
            serializer.save(tenant=tenant)
            return
        if not is_superadmin_user(self.request.user):
            raise PermissionDenied('Your account is not associated with a vendor tenant.')
        serializer.save()

    def list(self, request, *args, **kwargs):
        try:
            routers = list(self.filter_queryset(self.get_queryset()))
        except OperationalError as exc:
            return _database_error_response(exc, operation='list query')

        page = self.paginate_queryset(routers)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(routers, many=True)
        return Response(serializer.data)

    def _update_router(self, request, *, partial):
        router = self.get_object()
        payload = request.data.copy()
        if payload.get('api_ip') and not payload.get('nas_ip'):
            payload['nas_ip'] = payload['api_ip']
        payload.pop('api_ip', None)
        serializer = self.get_serializer(router, data=payload, partial=partial)
        serializer.is_valid(raise_exception=True)
        router = serializer.save()
        return Response(self.get_serializer(router).data, status=status.HTTP_200_OK)

    def update(self, request, *args, **kwargs):
        return self._update_router(request, partial=False)

    def partial_update(self, request, *args, **kwargs):
        return self._update_router(request, partial=True)

    @action(detail=True, methods=['get'])
    def config_script(self, request, pk=None):
        nas = self.get_object()
        script = (
            f"/system identity set name={nas.nasname}\n"
            f"/radius add service=hotspot address={nas.radius_server_ip or '10.10.0.5'} secret={nas.shared_secret or nas.secret}\n"
            "/ip hotspot profile set [ find default=yes ] use-radius=yes\n"
            "/ip hotspot user profile set [ find default=yes ] shared-users=1\n"
            "/ip hotspot walled-garden add dst-host=\"*.m-pesa.co.ke\" comment=\"M-Pesa bypass\"\n"
        )
        return Response({'script': script})

    @action(detail=True, methods=['post'])
    def provision(self, request, pk=None):
        nas = self.get_object()

        target_ip = request.data.get('api_ip') or request.data.get('nas_ip') or nas.nas_ip
        target_user = request.data.get('api_username') or nas.api_username or 'netpulse_admin'
        target_pass = request.data.get('api_password') or nas.api_password or '123'
        try:
            target_port = int(request.data.get('api_port') or nas.api_port or 8728)
        except (TypeError, ValueError):
            return Response(
                {'ok': False, 'success': False, 'message': 'Router API port must be a valid integer.', 'code': 'INVALID_ROUTER_PORT'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        radius_ip = request.data.get('radius_ip') or request.data.get('radius_server_ip') or request.data.get('address') or '192.168.56.1'
        if not isinstance(radius_ip, str) or not radius_ip.strip():
            return Response(
                {'ok': False, 'message': 'RADIUS Server IP (address) is required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer_data = {
            'nas_ip': target_ip,
            'api_port': target_port,
            'api_username': target_user,
            'api_password': target_pass,
        }

        serializer = NASSerializer(instance=nas, data=serializer_data, partial=True)
        serializer.is_valid(raise_exception=True)

        try:
            logger.debug('Attempting router provisioning connection to %s:%s', target_ip, target_port)
            from librouteros import connect

            connection = connect(
                host=request.data.get('nas_ip') or target_ip,
                username=request.data.get('api_username') or target_user,
                password=request.data.get('api_password') or target_pass,
                port=target_port,
                timeout=5.0,
            )
            connection.close()

            nas.nas_ip = request.data.get('nas_ip') or target_ip
            nas.api_port = target_port
            nas.api_username = request.data.get('api_username') or target_user
            nas.api_password = request.data.get('api_password') or target_pass
            nas.is_online = True
            nas.status = 'online'
            nas.last_ping = timezone.now()
            nas.save(update_fields=['nas_ip', 'api_port', 'api_username', 'api_password', 'is_online', 'status', 'last_ping', 'updated_at'])

            serializer = NASSerializer(nas)

            return Response(
                {'status': 'success', 'message': 'Successfully connected and updated router status to Online!', 'data': serializer.data},
                status=status.HTTP_200_OK,
            )
        except (TimeoutError, socket.timeout) as exc:
            logger.warning('Router provisioning timed out for NAS %s at %s:%s: %s', nas.pk, target_ip, target_port, exc)
            nas.is_online = False
            nas.status = 'offline'
            nas.save(update_fields=['is_online', 'status', 'updated_at'])
            return Response(
                {
                    'ok': False,
                    'success': False,
                    'message': 'Router connection timed out. Please check IP and port.',
                    'code': 'ROUTER_CONNECTION_TIMEOUT',
                    'is_online': False,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        except RouterConnectionError as exc:
            return Response(
                {'ok': False, 'success': False, 'message': str(exc), 'code': exc.code},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except OSError as exc:
            logger.warning('Router provisioning connection failed for NAS %s at %s:%s: %s', nas.pk, target_ip, target_port, exc)
            nas.is_online = False
            nas.status = 'offline'
            nas.save(update_fields=['is_online', 'status', 'updated_at'])
            return Response(
                {'ok': False, 'success': False, 'message': 'Unable to connect to the router. Please check IP, port, and credentials.', 'code': 'ROUTER_CONNECTION_FAILED', 'is_online': False},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception:  # Keep provisioning failures from leaking as unhandled 500 responses.
            logger.exception('Unexpected router provisioning failure for NAS %s', nas.pk)
            return Response(
                {'ok': False, 'success': False, 'message': 'Router provisioning failed. Please check the router settings and try again.', 'code': 'PROVISION_FAILED'},
                status=status.HTTP_400_BAD_REQUEST,
            )

    @action(detail=True, methods=['get'], url_path='metrics')
    def metrics(self, request, pk=None):
        router = self.get_object()
        try:
            return Response(fetch_router_metrics(router))
        except RouterConnectionError as exc:
            logger.warning('Metrics request failed for router %s: %s', router.pk, exc)
            return Response(
                {'detail': str(exc), 'code': exc.code},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        except Exception:
            logger.exception('Unexpected metrics failure for router %s', router.pk)
            return Response(
                {
                    'detail': 'Unable to retrieve live metrics from the router.',
                    'code': 'ROUTER_METRICS_FAILED',
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )

    @action(detail=True, methods=['post'])
    def reboot(self, request, pk=None):
        nas = self.get_object()
        return Response({'router_id': nas.id, 'status': 'reboot_requested'})

    @action(detail=True, methods=['post'])
    def health_check(self, request, pk=None):
        nas = self.get_object()
        try:
            result = update_router_health(nas, timeout=5.0)
            nas.refresh_from_db(fields=['is_online', 'last_ping'])
        except OperationalError as exc:
            return _database_error_response(exc, operation='health check')
        return Response({'router_id': nas.id, 'is_online': nas.is_online, 'last_ping': nas.last_ping, 'code': result['code'], 'message': result['message']})


class PortalConfigView(viewsets.ViewSet):
    permission_classes = [AllowAny]

    def retrieve(self, request, pk=None):
        try:
            nas = NAS.objects.get(id=pk)

            if nas.tenant.status != 'ACTIVE' or not nas.is_online:
                return Response(
                    {'error': 'Account suspended or router inactive', 'code': 'ROUTER_DISABLED'},
                    status=403,
                )

            from apps.billing.serializers import HotspotPlanSerializer
            data = {
                'business_name': nas.tenant.business_name,
                'headline': nas.tenant.welcome_headline or f"Welcome to {nas.tenant.business_name} Wi-Fi",
                'logo_url': nas.tenant.logo_url,
                'brand_color': nas.tenant.brand_color,
                'terms_of_service': nas.tenant.terms_of_service,
                'plans': HotspotPlanSerializer(nas.tenant.plans.filter(is_active=True), many=True).data,
            }
            return Response(data)
        except NAS.DoesNotExist:
            return Response({'error': 'NAS not found'}, status=404)
