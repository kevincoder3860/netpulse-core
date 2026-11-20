import logging

from celery import shared_task
from .models import NAS
from .services import check_router_status

logger = logging.getLogger(__name__)

@shared_task
def check_router_health():
    routers = NAS.objects.filter(type='mikrotik')
    for router in routers:
        _check_single_router(router)

def _check_single_router(router):
    try:
        return check_router_status(router)
    except (OSError, TimeoutError) as exc:
        host = getattr(router, 'nas_ip', None) or getattr(router, 'nasname', 'unknown')
        logger.warning('Router health check could not reach NAS %s (%s): %s', router.pk, host, exc)
        return {
            'is_online': False,
            'status': 'offline',
            'error': str(exc),
        }

@shared_task
def ping_router_task(router_id):
    try:
        router = NAS.objects.get(id=router_id)
        return _check_single_router(router)
    except NAS.DoesNotExist:
        return {'is_online': False, 'status': 'offline', 'error': 'Router not found'}
