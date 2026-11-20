from datetime import timedelta
from decimal import Decimal
from datetime import datetime
import logging

import psutil
from django.db import OperationalError
from django.db.models import Sum, Count, Max
from django.core.cache import cache
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.billing.models import Transaction
from apps.routers.models import NAS
from core.permissions import IsSuperAdminOrVendor, tenant_for_user
from .models import ClientActivity, TrafficSample

logger = logging.getLogger(__name__)

ROUTER_TELEMETRY_CACHE_SECONDS = 15


def _router_telemetry(router):
    """
    Fetch live telemetry for a single NAS router.

    Delegates to fetch_router_telemetry (telemetry app) which uses
    routeros_api with plaintext_login=True (RouterOS v7+), a 5-second
    socket timeout, and a guaranteed pool.disconnect() in its finally block.

    Returns a dict with keys: cpu, memory, tx_bytes, rx_bytes, interface.
    On failure (auth error, timeout, offline) returns safe zero-valued defaults
    so callers never need to handle None.
    """
    cache_key = (
        f'router-telemetry-v1:{router.pk}:'
        f'{getattr(router, "nas_ip", "")}:{getattr(router, "api_port", "")}'
    )
    try:
        cached_sample = cache.get(cache_key)
    except Exception as exc:
        logger.warning('Router telemetry cache read failed for NAS %s: %s', router.pk, exc)
        cached_sample = None
    if cached_sample is not None:
        return cached_sample

    try:
        from apps.telemetry.views import fetch_router_telemetry
        sample = fetch_router_telemetry(router)
    except Exception as exc:
        logger.warning('Router telemetry failed for NAS %s: %s', router.pk, exc)
        result = {'cpu': 0.0, 'memory': 0.0, 'tx_bytes': 0, 'rx_bytes': 0, 'interface': 'unknown'}
    else:
        if sample.get('status') != 'online':
            result = {'cpu': 0.0, 'memory': 0.0, 'tx_bytes': 0, 'rx_bytes': 0, 'interface': 'unknown'}
        else:
            result = {
                'cpu': float(sample.get('cpu') or 0),
                'memory': float(sample.get('memory') or 0),
                'tx_bytes': int(sample.get('tx_bytes') or 0),
                'rx_bytes': int(sample.get('rx_bytes') or 0),
                'interface': sample.get('interface') or 'unknown',
            }

    try:
        cache.set(cache_key, result, timeout=ROUTER_TELEMETRY_CACHE_SECONDS)
    except Exception as exc:
        logger.warning('Router telemetry cache write failed for NAS %s: %s', router.pk, exc)
    return result



class TelemetryHealthView(APIView):
    permission_classes = [IsSuperAdminOrVendor]

    def get(self, request):
        tenant = tenant_for_user(request.user)
        tenant_id = request.query_params.get('tenant_id') if request.user.is_superadmin else getattr(tenant, 'id', None)
        try:
            routers = list(
                NAS.objects.filter(tenant_id=tenant_id, type='mikrotik', is_online=True)
            ) if tenant_id else []
            inactive_routers = (
                NAS.objects.filter(tenant_id=tenant_id, is_online=False).count()
                if tenant_id else 0
            )
            total_routers = NAS.objects.filter(tenant_id=tenant_id).count() if tenant_id else 0
            now = timezone.now()
            transactions = Transaction.objects.filter(tenant_id=tenant_id, status='COMPLETED')
            income_today = transactions.filter(
                created_at__date=now.date()
            ).aggregate(total=Sum('gross_amount'))['total'] or Decimal('0.00')
            income_month = transactions.filter(
                created_at__year=now.year,
                created_at__month=now.month,
            ).aggregate(total=Sum('gross_amount'))['total'] or Decimal('0.00')
        except OperationalError as exc:
            is_busy = 'locked' in str(exc).lower() or 'busy' in str(exc).lower()
            code = 'DATABASE_BUSY' if is_busy else 'DATABASE_UNAVAILABLE'
            logger.warning('Telemetry database query failed for tenant %s (%s): %s', tenant_id, code, exc)
            return Response(
                {'detail': 'Telemetry data is temporarily unavailable.', 'code': code},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

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

        return Response({
            'server_cpu': round(server_cpu, 2),
            'mikrotik_cpu': round(router_cpu, 2),
            'memory': round(memory, 2),
            'disk': round(disk, 2),
            'router_memory': round(router_memory, 2),
            'income_today': float(income_today),
            'income_month': float(income_month),
            'hotspot_status': {
                'active': len(routers),
                'inactive': inactive_routers,
                'total': total_routers,
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
