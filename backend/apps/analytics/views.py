from datetime import timedelta
from decimal import Decimal
from datetime import datetime
import logging

import psutil
from django.db.models import Sum, Count, Max
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.billing.models import Transaction
from apps.routers.models import NAS
from core.permissions import IsSuperAdminOrVendor, tenant_for_user
from .models import ClientActivity, TrafficSample

logger = logging.getLogger(__name__)

try:
    from librouteros import connect as routeros_connect
except Exception:  # pragma: no cover - optional at import time
    routeros_connect = None


def _router_telemetry(router):
    if routeros_connect is None:
        return {'cpu': 0.0, 'memory': 0.0, 'tx_bytes': 0, 'rx_bytes': 0, 'interface': 'unknown'}
    connection = None
    try:
        connection = routeros_connect(
            host=router.nas_ip,
            username=router.api_username,
            password=router.api_password,
            port=router.api_port or 8728,
        )
        resource = list(connection.path('/system/resource').select('cpu-load', 'free-memory', 'total-memory'))
        interfaces = list(connection.path('/interface').select('name', 'rx-byte', 'tx-byte'))
        resource = resource[0] if resource else {}
        total_memory = float(resource.get('total-memory', 0) or 0)
        free_memory = float(resource.get('free-memory', 0) or 0)
        memory = ((total_memory - free_memory) / total_memory * 100) if total_memory else 0.0
        traffic = max(
            interfaces,
            key=lambda item: int(item.get('rx-byte', 0) or 0) + int(item.get('tx-byte', 0) or 0),
            default={},
        )
        return {
            'cpu': float(resource.get('cpu-load', 0) or 0),
            'memory': round(memory, 2),
            'tx_bytes': int(traffic.get('tx-byte', 0) or 0),
            'rx_bytes': int(traffic.get('rx-byte', 0) or 0),
            'interface': traffic.get('name', 'unknown') or 'unknown',
        }
    except Exception as exc:
        logger.warning('Router telemetry failed for NAS %s: %s', router.pk, exc)
        return {'cpu': 0.0, 'memory': 0.0, 'tx_bytes': 0, 'rx_bytes': 0, 'interface': 'unknown'}
    finally:
        if connection is not None and hasattr(connection, 'close'):
            connection.close()


class TelemetryHealthView(APIView):
    permission_classes = [IsSuperAdminOrVendor]

    def get(self, request):
        tenant = tenant_for_user(request.user)
        tenant_id = request.query_params.get('tenant_id') if request.user.is_superadmin else getattr(tenant, 'id', None)
        routers = NAS.objects.filter(tenant_id=tenant_id, type='mikrotik', is_online=True) if tenant_id else NAS.objects.none()
        server_cpu = psutil.cpu_percent(interval=0)
        memory = psutil.virtual_memory().percent
        disk = psutil.disk_usage('/').percent
        router_cpu = 0.0
        router_memory = 0.0
        tx_bytes = 0
        rx_bytes = 0
        for router in routers:
            sample = _router_telemetry(router)
            router_cpu = max(router_cpu, sample['cpu'])
            router_memory = max(router_memory, sample['memory'])
            tx_bytes += sample['tx_bytes']
            rx_bytes += sample['rx_bytes']

        now = timezone.now()
        transactions = Transaction.objects.filter(tenant_id=tenant_id, status='COMPLETED')
        income_today = transactions.filter(created_at__date=now.date()).aggregate(total=Sum('gross_amount'))['total'] or Decimal('0.00')
        income_month = transactions.filter(created_at__year=now.year, created_at__month=now.month).aggregate(total=Sum('gross_amount'))['total'] or Decimal('0.00')
        return Response({
            'server_cpu': round(server_cpu, 2),
            'mikrotik_cpu': round(router_cpu, 2),
            'memory': round(memory, 2),
            'disk': round(disk, 2),
            'router_memory': round(router_memory, 2),
            'income_today': float(income_today),
            'income_month': float(income_month),
            'hotspot_status': {
                'active': routers.count(),
                'inactive': NAS.objects.filter(tenant_id=tenant_id, is_online=False).count() if tenant_id else 0,
                'total': NAS.objects.filter(tenant_id=tenant_id).count() if tenant_id else 0,
            },
            'traffic': {
                'tx_kbps': round(tx_bytes / 1024, 2),
                'rx_kbps': round(rx_bytes / 1024, 2),
                'timestamp': now.isoformat(),
            },
        })


class AnalyticsDashboardView(APIView):
    permission_classes = [IsSuperAdminOrVendor]

    def get(self, request):
        tenant = tenant_for_user(request.user)
        tenant_id = request.query_params.get('tenant_id') if request.user.is_superadmin else str(tenant.id)
        tx = Transaction.objects.filter(tenant_id=tenant_id, status='COMPLETED')
        routers = NAS.objects.filter(tenant_id=tenant_id)
        now = timezone.now()
        today = tx.filter(created_at__date=now.date())
        month = tx.filter(created_at__year=now.year, created_at__month=now.month)
        sample_qs = TrafficSample.objects.filter(tenant_id=tenant_id)
        latest_samples = sample_qs.order_by('-timestamp')[:24]
        latest = sample_qs.order_by('-timestamp').first()
        activity = ClientActivity.objects.filter(tenant_id=tenant_id, activity_date__gte=now.date() - timedelta(days=30))
        top = activity.values('mac_address').annotate(upload=Sum('upload_bytes'), download=Sum('download_bytes')).order_by('-download')[:10]
        daily = activity.values('activity_date').annotate(users=Count('mac_address', distinct=True)).order_by('activity_date')
        return Response({
            'income_today': today.aggregate(total=Sum('gross_amount'))['total'] or 0,
            'income_month': month.aggregate(total=Sum('gross_amount'))['total'] or 0,
            'active_users': activity.filter(activity_date=now.date()).values('mac_address').distinct().count(),
            'total_users': activity.values('mac_address').distinct().count(),
            'hotspot_status': {'active': routers.filter(is_online=True).count(), 'inactive': routers.filter(is_online=False).count(), 'total': routers.count()},
            'health': {'server_cpu': 0, 'mikrotik_cpu': latest.cpu_percent if latest else 0, 'memory': latest.memory_percent if latest else 0, 'disk': latest.disk_percent if latest else 0, 'router_memory': latest.router_memory_percent if latest else 0},
            'traffic': [{'timestamp': item.timestamp, 'tx_bytes': item.tx_bytes, 'rx_bytes': item.rx_bytes} for item in reversed(list(latest_samples))],
            'top_downloaders': list(top),
            'activity_calendar': list(daily),
        })
