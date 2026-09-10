from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from rest_framework.permissions import SAFE_METHODS
from django.db import DatabaseError
import logging
import socket
from django.utils import timezone

from .models import NAS
from .serializers import NASSerializer
from core.permissions import HasStaffPermission, IsSuperAdminOrVendor, IsVendorManager, tenant_for_user
from .services import RouterConnectionError, fetch_router_telemetry, ping_router_with_credentials, update_router_health, provision_mikrotik_router

logger = logging.getLogger(__name__)


class RouterViewSet(viewsets.ModelViewSet):
    queryset = NAS.objects.all()
    serializer_class = NASSerializer
    permission_classes = [IsSuperAdminOrVendor]

    def get_permissions(self):
        if self.request.method in SAFE_METHODS:
            return [HasStaffPermission('MANAGER', 'TECHNICIAN', 'CASHIER')]
        return [IsVendorManager()]

    def get_queryset(self):
        queryset = super().get_queryset()
        tenant_id = self.request.query_params.get('tenant_id')
        if self.request.user.is_superadmin:
            return queryset.filter(tenant_id=tenant_id) if tenant_id else queryset
        tenant = tenant_for_user(self.request.user)
        if tenant:
            return queryset.filter(tenant_id=tenant.id)
        return queryset.none()

    def _update_router_and_ping(self, request, *, partial):
        router = self.get_object()
        payload = request.data.copy()
        if payload.get('api_ip') and not payload.get('nas_ip'):
            payload['nas_ip'] = payload['api_ip']
        payload.pop('api_ip', None)
        serializer = self.get_serializer(router, data=payload, partial=partial)
        serializer.is_valid(raise_exception=True)
        api_ip = payload.get('api_ip') or payload.get('nas_ip')
        api_user = payload.get('api_username')
        api_pass = payload.get('api_password')
        api_port = payload.get('api_port')
        try:
            host, port, username, password = ping_router_with_credentials(
                router,
                api_ip=api_ip,
                api_port=api_port,
                api_username=api_user,
                api_password=api_pass,
            )
            router = serializer.save(
                nas_ip=host,
                api_port=port,
                api_username=username,
                api_password=password,
                is_online=True,
                status='online',
                last_ping=timezone.now(),
            )
            return Response(self.get_serializer(router).data, status=status.HTTP_200_OK)
        except Exception as exc:
            router.is_online = False
            router.status = 'offline'
            router.save(update_fields=['is_online', 'status', 'updated_at'])
            code = getattr(exc, 'code', 'ROUTER_UNREACHABLE')
            return Response({'ok': False, 'success': False, 'message': str(exc), 'code': code, 'is_online': False}, status=status.HTTP_400_BAD_REQUEST)

    def update(self, request, *args, **kwargs):
        return self._update_router_and_ping(request, partial=False)

    def partial_update(self, request, *args, **kwargs):
        return self._update_router_and_ping(request, partial=True)

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
        connection = None

        def mark_offline():
            nas.is_online = False
            nas.status = 'offline'
            nas.save()

        try:
            target_ip = request.data.get('nas_ip') or request.data.get('api_ip') or nas.nas_ip
            target_user = request.data.get('api_username') or nas.api_username or 'netpulse_admin'
            target_pass = request.data.get('api_password') or nas.api_password or '123'
            target_port = int(request.data.get('api_port') or nas.api_port or 8728)
            if not target_ip:
                raise ValueError('Router IP is required.')

            serializer = NASSerializer(instance=nas, data={
                'nas_ip': target_ip,
                'api_port': target_port,
                'api_username': target_user,
                'api_password': target_pass,
            }, partial=True)
            serializer.is_valid(raise_exception=True)

            from librouteros import connect
            connection = connect(
                host=target_ip,
                username=target_user,
                password=target_pass,
                port=target_port,
            )

            serializer.save(
                nas_ip=target_ip,
                api_port=target_port,
                api_username=target_user,
                api_password=target_pass,
                is_online=True,
                status='online',
                last_ping=timezone.now(),
            )

            return Response(
                {'status': 'success', 'message': 'Successfully connected and updated router status to Online!', 'data': NASSerializer(nas).data},
                status=status.HTTP_200_OK,
            )
        except serializers.ValidationError as exc:
            logger.warning('Router provisioning validation failed for NAS %s: %s', nas.pk, exc.detail)
            return Response({'status': 'failed', 'message': str(exc.detail), 'code': 'VALIDATION_FAILED'}, status=status.HTTP_400_BAD_REQUEST)
        except RouterConnectionError as exc:
            mark_offline()
            return Response(
                {'success': False, 'is_online': False, 'status': 'offline', 'message': 'Router is unreachable and marked as offline.'},
                status=status.HTTP_200_OK,
            )
        except (TimeoutError, ConnectionError, OSError) as exc:
            mark_offline()
            logger.warning('Router %s is unreachable: %s', nas.pk, exc)
            return Response(
                {'success': False, 'is_online': False, 'status': 'offline', 'message': 'Router is unreachable and marked as offline.'},
                status=status.HTTP_200_OK,
            )
        except (DatabaseError, ValueError, TypeError) as exc:
            logger.exception('Router provisioning failure for NAS %s', nas.pk)
            return Response(
                {'ok': False, 'success': False, 'message': str(exc), 'code': 'PROVISION_FAILED'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as exc:
            mark_offline()
            logger.exception('Unexpected router provisioning failure for NAS %s', nas.pk)
            return Response(
                {'success': False, 'is_online': False, 'status': 'offline', 'message': 'Router is unreachable and marked as offline.'},
                status=status.HTTP_200_OK,
            )
        finally:
            if connection is not None:
                try:
                    connection.close()
                except Exception:
                    logger.warning('Unable to close router connection for NAS %s', nas.pk, exc_info=True)

    @action(detail=True, methods=['post'])
    def reboot(self, request, pk=None):
        nas = self.get_object()
        return Response({'router_id': nas.id, 'status': 'reboot_requested'})

    @action(detail=True, methods=['post'])
    def health_check(self, request, pk=None):
        nas = self.get_object()
        try:
            with socket.create_connection((nas.nas_ip or nas.nasname, nas.api_port or 8728), timeout=2):
                pass
        except (OSError, TimeoutError, ValueError):
            nas.is_online = False
            nas.status = 'offline'
            nas.save(update_fields=['is_online', 'status', 'updated_at'])
            return Response({
                'is_online': False,
                'status': 'offline',
                'telemetry': None,
                'message': 'Router offline',
            }, status=status.HTTP_200_OK)
        result = update_router_health(nas, timeout=2.0)
        nas.refresh_from_db(fields=['is_online', 'status', 'last_ping'])
        return Response({
            'router_id': nas.id,
            'is_online': nas.is_online,
            'status': nas.status,
            'telemetry': None,
            'last_ping': nas.last_ping,
            'code': result['code'],
            'message': result['message'],
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'])
    def stats(self, request):
        routers = self.get_queryset()
        total = routers.count()
        online = routers.filter(is_online=True).count()
        return Response({
            'total_routers': total,
            'online_routers': online,
            'offline_routers': total - online,
        }, status=status.HTTP_200_OK)

    @action(detail=True, methods=['get'])
    def telemetry(self, request, pk=None):
        router = self.get_object()
        host = (router.nas_ip or router.nasname or '').strip()
        port = router.api_port or 8728
        try:
            with socket.create_connection((host, port), timeout=2):
                pass
        except (OSError, TimeoutError, ValueError):
            router.is_online = False
            router.status = 'offline'
            router.save(update_fields=['is_online', 'status', 'updated_at'])
            return Response({
                'is_online': False,
                'status': 'offline',
                'telemetry': None,
                'message': 'Router offline',
            }, status=status.HTTP_200_OK)

        try:
            telemetry = fetch_router_telemetry(router)
        except Exception:
            router.is_online = False
            router.status = 'offline'
            router.save(update_fields=['is_online', 'status', 'updated_at'])
            return Response({
                'is_online': False,
                'status': 'offline',
                'telemetry': None,
            }, status=status.HTTP_200_OK)

        router.is_online = True
        router.status = 'online'
        router.last_ping = timezone.now()
        router.save(update_fields=['is_online', 'status', 'last_ping', 'updated_at'])
        return Response({
            'is_online': True,
            'status': 'online',
            'telemetry': telemetry,
        }, status=status.HTTP_200_OK)

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
