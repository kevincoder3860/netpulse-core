import asyncio
import json
import logging
import os
from decimal import Decimal
from urllib.parse import parse_qs

import psutil
from asgiref.sync import sync_to_async
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.contrib.auth import get_user_model
from django.db.models import Sum
from django.utils import timezone
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import AccessToken

from apps.analytics.views import _router_telemetry
from apps.billing.models import Transaction
from apps.routers.models import NAS
from core.permissions import tenant_for_user

logger = logging.getLogger(__name__)
User = get_user_model()

STREAM_INTERVAL_SECONDS = 3.5
DISK_ROOT = os.path.abspath(os.sep)


def _host_metrics_sync() -> dict:
    """Blocking psutil sampling — must run off the event loop."""
    server_cpu = psutil.cpu_percent(interval=None)
    memory = psutil.virtual_memory().percent
    try:
        disk = psutil.disk_usage(DISK_ROOT).percent
    except OSError:
        disk = 0.0
    return {
        'server_cpu': round(server_cpu, 2),
        'memory': round(memory, 2),
        'disk': round(disk, 2),
    }


def _tenant_metrics_sync(tenant_id: str) -> dict:
    """Blocking ORM + RouterOS sampling — must run off the event loop."""
    host = _host_metrics_sync()

    online_routers = list(
        NAS.objects.filter(tenant_id=tenant_id, type='mikrotik', is_online=True)
    )
    total_routers = NAS.objects.filter(tenant_id=tenant_id).count()
    offline_routers = NAS.objects.filter(tenant_id=tenant_id, is_online=False).count()

    router_cpu = 0.0
    router_memory = 0.0
    tx_bytes = 0
    rx_bytes = 0
    primary_interface = 'unknown'
    busiest = -1

    for router in online_routers:
        try:
            sample = _router_telemetry(router)
        except Exception as exc:
            logger.warning('Router sample failed for NAS %s: %s', getattr(router, 'pk', '?'), exc)
            continue
        router_cpu = max(router_cpu, float(sample.get('cpu') or 0))
        router_memory = max(router_memory, float(sample.get('memory') or 0))
        sample_tx = int(sample.get('tx_bytes') or 0)
        sample_rx = int(sample.get('rx_bytes') or 0)
        tx_bytes += sample_tx
        rx_bytes += sample_rx
        load = sample_tx + sample_rx
        if load >= busiest:
            busiest = load
            primary_interface = sample.get('interface') or 'unknown'

    now = timezone.now()
    transactions = Transaction.objects.filter(tenant_id=tenant_id, status='COMPLETED')
    income_today = (
        transactions.filter(created_at__date=now.date()).aggregate(total=Sum('gross_amount'))['total']
        or Decimal('0.00')
    )
    income_month = (
        transactions.filter(created_at__year=now.year, created_at__month=now.month).aggregate(
            total=Sum('gross_amount')
        )['total']
        or Decimal('0.00')
    )

    return {
        **host,
        'mikrotik_cpu': round(router_cpu, 2),
        'router_memory': round(router_memory, 2),
        'income_today': float(income_today),
        'income_month': float(income_month),
        'hotspot_status': {
            'active': len(online_routers),
            'inactive': offline_routers,
            'total': total_routers,
        },
        'router_stats': {
            'total_routers': total_routers,
            'online_routers': len(online_routers),
            'offline_routers': offline_routers,
        },
        'live_telemetry': (
            {
                'rx_bytes': rx_bytes,
                'tx_bytes': tx_bytes,
                'interface': primary_interface,
            }
            if online_routers
            else None
        ),
        'traffic': {
            'tx_kbps': round(tx_bytes / 1024, 2),
            'rx_kbps': round(rx_bytes / 1024, 2),
            'timestamp': now.isoformat(),
        },
    }


def _fallback_payload() -> dict:
    """Host-only snapshot when tenant/router collection fails."""
    try:
        host = _host_metrics_sync()
    except Exception:
        host = {'server_cpu': 0.0, 'memory': 0.0, 'disk': 0.0}
    return {
        **host,
        'mikrotik_cpu': 0.0,
        'router_memory': 0.0,
        'income_today': 0.0,
        'income_month': 0.0,
        'hotspot_status': {'active': 0, 'inactive': 0, 'total': 0},
        'router_stats': {'total_routers': 0, 'online_routers': 0, 'offline_routers': 0},
        'live_telemetry': None,
        'traffic': {
            'tx_kbps': 0.0,
            'rx_kbps': 0.0,
            'timestamp': timezone.now().isoformat(),
        },
    }


class TelemetryConsumer(AsyncWebsocketConsumer):
    """Push host + router health snapshots over WebSocket for a tenant."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.tenant_id = None
        self.user = None
        self._stream_task = None
        self.keep_streaming = False

    async def connect(self):
        self.tenant_id = self.scope['url_route']['kwargs']['tenant_id']
        try:
            self.user = await self._authenticate()
            if self.user is None:
                logger.warning('Telemetry WS rejected: missing/invalid token tenant=%s', self.tenant_id)
                await self.close(code=4401)
                return
            if not await self._user_may_access_tenant(self.user, self.tenant_id):
                logger.warning('Telemetry WS rejected: forbidden tenant=%s user=%s', self.tenant_id, self.user.pk)
                await self.close(code=4403)
                return

            await self.accept()
            self.keep_streaming = True
            self._stream_task = asyncio.create_task(
                self.stream_telemetry(),
                name=f'telemetry-{self.tenant_id}',
            )
            logger.info('Telemetry WS connected tenant=%s', self.tenant_id)
        except Exception:
            logger.exception('Telemetry WS connect() failed for tenant %s', self.tenant_id)
            self.keep_streaming = False
            try:
                await self.close(code=1011)
            except Exception:
                pass

    async def disconnect(self, close_code):
        self.keep_streaming = False
        await self._stop_stream_task()
        logger.info('Telemetry WS disconnected tenant=%s code=%s', self.tenant_id, close_code)

    async def receive(self, text_data=None, bytes_data=None):
        if not text_data:
            return
        try:
            payload = json.loads(text_data)
        except json.JSONDecodeError:
            logger.warning('Telemetry WS received invalid JSON for tenant %s', self.tenant_id)
            return

        action = payload.get('action')
        if action == 'pause':
            self.keep_streaming = False
            await self._stop_stream_task()
            logger.debug('Telemetry stream paused tenant=%s', self.tenant_id)
        elif action == 'resume' and (self._stream_task is None or self._stream_task.done()):
            self.keep_streaming = True
            self._stream_task = asyncio.create_task(
                self.stream_telemetry(),
                name=f'telemetry-{self.tenant_id}',
            )
            logger.debug('Telemetry stream resumed tenant=%s', self.tenant_id)

    async def stream_telemetry(self):
        """Emit metrics while keep_streaming is True; never crash the ASGI worker."""
        collect = sync_to_async(_tenant_metrics_sync, thread_sensitive=True)
        fallback = sync_to_async(_fallback_payload, thread_sensitive=True)

        try:
            while self.keep_streaming:
                payload = None
                try:
                    payload = await collect(self.tenant_id)
                except Exception:
                    logger.exception(
                        'Telemetry metric collection failed for tenant %s — sending host fallback',
                        self.tenant_id,
                    )
                    try:
                        payload = await fallback()
                    except Exception:
                        logger.exception('Telemetry fallback also failed for tenant %s', self.tenant_id)
                        payload = None

                if not self.keep_streaming:
                    break

                if payload is not None:
                    try:
                        await self.send(text_data=json.dumps(payload))
                    except Exception as exc:
                        logger.info(
                            'Telemetry send failed for tenant %s (client likely gone): %s',
                            self.tenant_id,
                            exc,
                        )
                        self.keep_streaming = False
                        break

                try:
                    await asyncio.sleep(STREAM_INTERVAL_SECONDS)
                except asyncio.CancelledError:
                    raise
        except asyncio.CancelledError:
            logger.debug('Telemetry stream cancelled for tenant %s', self.tenant_id)
        except Exception:
            logger.exception('Telemetry stream crashed for tenant %s', self.tenant_id)
        finally:
            # Stop the loop flag only — do NOT close the socket here.
            # Closing from the stream task caused CONNECT→DISCONNECT reconnect storms.
            self.keep_streaming = False
            logger.debug('Telemetry stream loop ended for tenant %s', self.tenant_id)

    async def _stop_stream_task(self):
        task = self._stream_task
        self._stream_task = None
        if task is None or task.done():
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.debug(
                'Telemetry stream task cleanup error for tenant %s',
                self.tenant_id,
                exc_info=True,
            )

    async def _authenticate(self):
        query = parse_qs(self.scope.get('query_string', b'').decode())
        raw_token = (query.get('token') or [None])[0]
        if not raw_token:
            user = self.scope.get('user')
            if user is not None and getattr(user, 'is_authenticated', False):
                return user
            return None
        try:
            # AccessToken() performs HMAC crypto — run it off the event loop
            # so it cannot block the async worker and stall the handshake.
            def _validate_and_load():
                validated = AccessToken(raw_token)
                user_id = validated.get('user_id')
                if not user_id:
                    return None
                return (
                    User.objects.select_related('tenant_profile', 'staff_profile')
                    .get(pk=user_id)
                )

            return await database_sync_to_async(_validate_and_load)()
        except (InvalidToken, TokenError, User.DoesNotExist) as exc:
            logger.info('Telemetry JWT auth failed: %s', exc)
            return None

    @database_sync_to_async
    def _user_may_access_tenant(self, user, tenant_id: str) -> bool:
        if getattr(user, 'is_superadmin', False):
            return True
        tenant = tenant_for_user(user)
        return bool(tenant and str(tenant.id) == str(tenant_id))
