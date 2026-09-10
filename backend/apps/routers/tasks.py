import socket
import subprocess
import logging
import platform
from celery import shared_task
from django.utils import timezone
from .models import NAS

logger = logging.getLogger(__name__)

def ping_host(host):
    try:
        # Determine the ping argument based on the OS
        param = '-n' if platform.system().lower() == 'windows' else '-c'
        # -w 2000 for 2 seconds timeout. On Unix it's -W 2 (seconds), Windows is -w 2000 (ms)
        timeout_param = '-w' if platform.system().lower() == 'windows' else '-W'
        timeout_val = '2000' if platform.system().lower() == 'windows' else '2'
        
        output = subprocess.run(['ping', param, '1', timeout_param, timeout_val, host], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return output.returncode == 0
    except Exception as e:
        logger.error(f"Ping failed for {host}: {e}")
        return False

@shared_task
def check_router_health():
    routers = NAS.objects.all()
    for router in routers:
        _check_single_router(router)

def _check_single_router(router):
    host = router.nas_ip or router.nasname
    if not host:
        return {'is_online': False, 'status': 'offline', 'error': 'No IP or hostname provided'}
        
    port = router.api_port or 8728
    is_reachable = False
    error_msg = ""
    
    try:
        with socket.create_connection((host, port), timeout=2):
            is_reachable = True
    except (OSError, TimeoutError, ValueError) as e:
        error_msg = str(e)
        logger.info(f"Socket connection to {host}:{port} failed: {error_msg}. Falling back to ping.")
        is_reachable = ping_host(host)
        if not is_reachable:
            error_msg += " AND ping failed"
            
    if is_reachable:
        router.is_online = True
        router.status = 'online'
        router.last_ping = timezone.now()
        router.save(update_fields=['is_online', 'status', 'last_ping', 'updated_at'])
        logger.info(f"Router {host} is ONLINE")
    else:
        router.is_online = False
        router.status = 'offline'
        router.save(update_fields=['is_online', 'status', 'updated_at'])
        logger.error(f"Router {host} is OFFLINE: {error_msg}")
        
    return {
        'is_online': is_reachable,
        'status': router.status,
        'error': error_msg if not is_reachable else '',
        'last_ping': router.last_ping
    }

@shared_task
def ping_router_task(router_id):
    try:
        router = NAS.objects.get(id=router_id)
        return _check_single_router(router)
    except NAS.DoesNotExist:
        return {'is_online': False, 'status': 'offline', 'error': 'Router not found'}
