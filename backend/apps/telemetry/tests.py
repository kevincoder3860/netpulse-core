"""
Tests for backend/apps/telemetry/views.py:
    - Database configuration selection
  - plaintext_login=True passed to RouterOsApiPool
  - socket_timeout=5.0 passed to RouterOsApiPool
  - RouterOsApiCommunicationError → offline + "Authentication or protocol error"
  - RouterOsApiConnectionError    → offline + "Authentication or protocol error"
  - socket.timeout                → offline + error string
  - pool.disconnect() always called
  - TelemetryView always returns HTTP 200
"""

import socket
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
import json

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.cache import cache
from django.db import OperationalError
from django.test import SimpleTestCase, TestCase
from rest_framework.test import APIRequestFactory
from channels.testing import WebsocketCommunicator

from apps.telemetry.views import fetch_router_telemetry, TelemetryView
from apps.telemetry.consumers import TelemetryConsumer
from apps.analytics.views import _router_telemetry
from apps.routers.services import fetch_router_telemetry as router_services_fetch_telemetry
from apps.radius.models import Nas as RadiusNas
from apps.routers.models import NAS as RouterNAS
from core.db_routers import RadiusRouter
from core.settings import BASE_DIR, _default_database_config
from core.asgi import application

try:
    from routeros_api.exceptions import (
        RouterOsApiCommunicationError,
        RouterOsApiConnectionError,
    )
except ImportError:
    RouterOsApiCommunicationError = Exception  # type: ignore[assignment, misc]
    RouterOsApiConnectionError = Exception  # type: ignore[assignment, misc]


_POOL_PATH = 'apps.telemetry.views.RouterOsApiPool'
_SERVICES_POOL_PATH = 'apps.routers.services.RouterOsApiPool'


class RouterTelemetryCacheTests(SimpleTestCase):
    @patch('apps.telemetry.views.fetch_router_telemetry')
    def test_reuses_router_sample_for_the_cache_window(self, fetch_telemetry):
        router = SimpleNamespace(
            pk=f'cache-test-{uuid.uuid4()}',
            nas_ip='192.0.2.50',
            api_port=8728,
        )
        cache_key = f'router-telemetry-v1:{router.pk}:{router.nas_ip}:{router.api_port}'
        sample = {
            'status': 'online',
            'cpu': 12,
            'memory': 34,
            'tx_bytes': 56,
            'rx_bytes': 78,
            'interface': 'ether1',
        }
        fetch_telemetry.return_value = sample
        try:
            first = _router_telemetry(router)
            second = _router_telemetry(router)
        finally:
            cache.delete(cache_key)

        self.assertEqual(first, second)
        self.assertEqual(first['interface'], 'ether1')
        fetch_telemetry.assert_called_once_with(router)
_SERVICES_AVAIL_PATH = 'apps.routers.services._ROUTEROS_API_AVAILABLE'
_AVAIL_PATH = 'apps.telemetry.views._ROUTEROS_API_AVAILABLE'


class TelemetryDatabaseSettingsTests(SimpleTestCase):
    def test_default_database_uses_sqlite_without_postgres_configuration(self):
        config = _default_database_config({})
        self.assertEqual(config['ENGINE'], 'django.db.backends.sqlite3')
        self.assertEqual(config['NAME'], BASE_DIR / 'db.sqlite3')
        self.assertEqual(config['OPTIONS']['timeout'], 5)

    def test_sqlite_database_url_uses_bounded_lock_timeout(self):
        config = _default_database_config({'DATABASE_URL': 'sqlite:///telemetry-tests.sqlite3'})
        self.assertEqual(config['ENGINE'], 'django.db.backends.sqlite3')
        self.assertEqual(config['OPTIONS']['timeout'], 5)

    def test_router_credential_encryption_has_a_configured_key(self):
        self.assertTrue(settings.CREDENTIAL_ENCRYPTION_KEY)
        self.assertEqual(
            settings.REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']['paystack_stk'],
            '10/minute',
        )

    def test_database_url_selects_postgresql(self):
        config = _default_database_config({'DATABASE_URL': 'postgresql://db.example/netpulse'})
        self.assertEqual(config['ENGINE'], 'django.db.backends.postgresql')
        self.assertEqual(config['HOST'], 'db.example')
        self.assertEqual(config['NAME'], 'netpulse')

    def test_database_url_takes_priority_over_compose_variables(self):
        config = _default_database_config({
            'DATABASE_URL': 'postgresql://url.example/url_database',
            'POSTGRES_DB': 'compose_database',
            'POSTGRES_USER': 'compose_user',
            'POSTGRES_PASSWORD': 'test-only',
            'POSTGRES_HOST': 'db',
        })
        self.assertEqual(config['HOST'], 'url.example')
        self.assertEqual(config['NAME'], 'url_database')

    def test_compose_environment_selects_postgresql(self):
        config = _default_database_config({
            'POSTGRES_DB': 'netpulse',
            'POSTGRES_USER': 'netpulse_user',
            'POSTGRES_PASSWORD': 'test-only',
            'POSTGRES_HOST': 'db',
        })
        self.assertEqual(config['ENGINE'], 'django.db.backends.postgresql')
        self.assertEqual(config['HOST'], 'db')
        self.assertEqual(config['NAME'], 'netpulse')

    def test_invalid_or_incomplete_postgresql_configuration_fails(self):
        invalid_configs = (
            {'DATABASE_URL': ''},
            {'DATABASE_URL': 'postgresql://db.example/'},
            {'POSTGRES_HOST': 'db'},
        )
        for environ in invalid_configs:
            with self.subTest(configured_keys=sorted(environ)):
                with self.assertRaises(ImproperlyConfigured):
                    _default_database_config(environ)

    def test_radius_alias_and_router_remain_separate(self):
        radius_config = settings.DATABASES['radius_db']
        self.assertEqual(radius_config['ENGINE'], 'django.db.backends.sqlite3')
        self.assertEqual(radius_config['OPTIONS']['timeout'], 5)

        router = RadiusRouter()
        self.assertEqual(router.db_for_read(RadiusNas), 'radius_db')
        self.assertEqual(router.db_for_write(RadiusNas), 'radius_db')
        self.assertIsNone(router.db_for_read(RouterNAS))
        self.assertFalse(router.allow_migrate('default', 'radius'))
        self.assertTrue(router.allow_migrate('radius_db', 'radius'))
        self.assertFalse(router.allow_migrate('radius_db', 'billing'))
        self.assertIsNone(router.allow_migrate('default', 'routers'))
        self.assertTrue(router.allow_relation(RadiusNas(), RouterNAS()))


class TelemetryWebSocketRoutingTests(SimpleTestCase):
    async def test_asgi_application_routes_telemetry_websocket(self):
        tenant_id = uuid.uuid4()
        communicator = WebsocketCommunicator(application, f'/ws/telemetry/{tenant_id}/')
        connected, close_code = await communicator.connect()

        self.assertFalse(connected)
        self.assertEqual(close_code, 4401)
        await communicator.disconnect()


class TelemetryStreamDatabaseErrorTests(SimpleTestCase):
    async def test_database_lock_sends_host_fallback_over_websocket(self):
        consumer = TelemetryConsumer()
        consumer.tenant_id = str(uuid.uuid4())
        consumer.keep_streaming = True
        sent_payloads = []

        async def send_payload(*, text_data):
            sent_payloads.append(json.loads(text_data))
            consumer.keep_streaming = False

        async def fail_collection(_tenant_id):
            raise OperationalError('database is locked')

        async def host_fallback():
            return {'fallback': True}

        consumer.send = send_payload
        with (
            patch(
                'apps.telemetry.consumers.database_sync_to_async',
                return_value=fail_collection,
            ),
            patch(
                'apps.telemetry.consumers.sync_to_async',
                return_value=host_fallback,
            ),
            patch('apps.telemetry.consumers.asyncio.sleep', new_callable=AsyncMock),
            self.assertLogs('apps.telemetry.consumers', level='WARNING'),
        ):
            await consumer.stream_telemetry()

        self.assertEqual(sent_payloads, [{'fallback': True}])


class FetchRouterTelemetryViewsTests(TestCase):
    """Tests targeting apps.telemetry.views.fetch_router_telemetry."""

    def _mock_pool(self, mock_cls, interfaces=None, resource=None):
        """Return a configured pool mock whose get_api() works."""
        pool = MagicMock()
        api = MagicMock()
        iface_res = MagicMock()
        sys_res = MagicMock()

        mock_cls.return_value = pool
        pool.get_api.return_value = api
        api.get_resource.side_effect = lambda path: iface_res if '/interface' in path else sys_res
        iface_res.get.return_value = interfaces if interfaces is not None else []
        sys_res.get.return_value = resource if resource is not None else []
        return pool

    @patch(_POOL_PATH)
    def test_passes_plaintext_login_true(self, mock_cls):
        self._mock_pool(mock_cls)
        fetch_router_telemetry('192.168.56.20')
        _, kwargs = mock_cls.call_args
        self.assertTrue(kwargs.get('plaintext_login'), 'plaintext_login must be True for RouterOS v7')

    @patch(_POOL_PATH)
    def test_passes_socket_timeout_5(self, mock_cls):
        self._mock_pool(mock_cls)
        fetch_router_telemetry('192.168.56.20')
        _, kwargs = mock_cls.call_args
        self.assertEqual(kwargs.get('socket_timeout'), 5.0)

    @patch(_POOL_PATH)
    def test_passes_port_8728(self, mock_cls):
        self._mock_pool(mock_cls)
        fetch_router_telemetry('192.168.56.20')
        _, kwargs = mock_cls.call_args
        self.assertEqual(kwargs.get('port'), 8728)

    @patch(_POOL_PATH)
    def test_returns_online_on_success(self, mock_cls):
        self._mock_pool(mock_cls)
        data = fetch_router_telemetry('192.168.56.20')
        self.assertEqual(data['status'], 'online')

    @patch(_POOL_PATH)
    def test_disconnect_called_on_success(self, mock_cls):
        pool = self._mock_pool(mock_cls)
        fetch_router_telemetry('192.168.56.20')
        pool.disconnect.assert_called_once()

    @patch(_POOL_PATH)
    def test_communication_error_returns_auth_fallback(self, mock_cls):
        pool = MagicMock()
        mock_cls.return_value = pool
        pool.get_api.side_effect = RouterOsApiCommunicationError('bad login', 'bad login')

        with self.assertLogs('apps.telemetry.views', level='WARNING') as cm:
            data = fetch_router_telemetry('192.168.56.20')

        self.assertEqual(data['status'], 'offline')
        self.assertEqual(data.get('detail'), 'Authentication or protocol error')
        self.assertFalse(any(k == 'error' for k in data), 'auth failures must use "detail" not "error"')
        self.assertTrue(any('[Telemetry Auth Error] Router 192.168.56.20' in log for log in cm.output))
        pool.disconnect.assert_called_once()

    @patch(_POOL_PATH)
    def test_connection_error_returns_auth_fallback(self, mock_cls):
        pool = MagicMock()
        mock_cls.return_value = pool
        pool.get_api.side_effect = RouterOsApiConnectionError('connection refused')

        with self.assertLogs('apps.telemetry.views', level='WARNING') as cm:
            data = fetch_router_telemetry('192.168.56.20')

        self.assertEqual(data['status'], 'offline')
        self.assertEqual(data.get('detail'), 'Authentication or protocol error')
        self.assertTrue(any('[Telemetry Connection Error] Router 192.168.56.20' in log for log in cm.output))
        pool.disconnect.assert_called_once()

    @patch(_POOL_PATH)
    def test_socket_timeout_returns_offline_with_error(self, mock_cls):
        pool = MagicMock()
        mock_cls.return_value = pool
        pool.get_api.side_effect = socket.timeout('timed out')

        with self.assertLogs('apps.telemetry.views', level='WARNING') as cm:
            data = fetch_router_telemetry('192.168.56.20')

        self.assertEqual(data['status'], 'offline')
        self.assertIn('error', data)
        self.assertNotIn('detail', data)
        self.assertTrue(any('[Telemetry Timeout] Router 192.168.56.20 unreachable (timed out)' in log for log in cm.output))
        pool.disconnect.assert_called_once()

    @patch(_POOL_PATH)
    def test_interface_query_timeout_is_reported_as_offline(self, mock_cls):
        pool = MagicMock()
        api = MagicMock()
        interface_resource = MagicMock()
        system_resource = MagicMock()
        mock_cls.return_value = pool
        pool.get_api.return_value = api
        api.get_resource.side_effect = (
            lambda path: interface_resource if '/interface' in path else system_resource
        )
        interface_resource.get.side_effect = socket.timeout('interface query timed out')

        with self.assertLogs('apps.telemetry.views', level='WARNING') as logs:
            data = fetch_router_telemetry('192.168.56.20')

        self.assertEqual(data['status'], 'offline')
        self.assertEqual(data['error'], 'interface query timed out')
        self.assertTrue(any('[Telemetry Timeout]' in message for message in logs.output))
        pool.disconnect.assert_called_once()

    @patch(_POOL_PATH)
    def test_disconnect_called_even_on_error(self, mock_cls):
        pool = MagicMock()
        mock_cls.return_value = pool
        pool.get_api.side_effect = RuntimeError('unexpected')
        fetch_router_telemetry('192.168.56.20')
        pool.disconnect.assert_called_once()

    @patch('apps.telemetry.views.fetch_router_telemetry')
    def test_telemetry_view_returns_http_200_on_auth_fallback(self, mock_fetch):
        mock_fetch.return_value = {'status': 'offline', 'detail': 'Authentication or protocol error'}
        factory = APIRequestFactory()
        request = factory.get('/api/v1/telemetry/?host=192.168.56.20')
        response = TelemetryView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data.get('status'), 'offline')
        self.assertEqual(response.data.get('detail'), 'Authentication or protocol error')

    @patch('apps.telemetry.views.fetch_router_telemetry')
    def test_telemetry_view_returns_http_200_on_timeout(self, mock_fetch):
        mock_fetch.return_value = {'status': 'offline', 'error': 'timed out'}
        factory = APIRequestFactory()
        request = factory.get('/api/v1/telemetry/?host=192.168.56.20')
        response = TelemetryView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data.get('status'), 'offline')

    @patch('apps.routers.models.NAS.objects.filter', side_effect=OperationalError('database is locked'))
    def test_telemetry_view_returns_service_unavailable_when_router_lookup_is_locked(self, _mock_filter):
        factory = APIRequestFactory()
        request = factory.get('/api/v1/telemetry/1/')
        response = TelemetryView.as_view()(request, pk='1')

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data['code'], 'DATABASE_BUSY')


class FetchRouterTelemetryServicesTests(TestCase):
    """Tests targeting apps.routers.services.fetch_router_telemetry."""

    @patch(_SERVICES_AVAIL_PATH, True)
    @patch(_SERVICES_POOL_PATH)
    def test_passes_plaintext_login_true(self, mock_cls):
        pool = MagicMock()
        mock_cls.return_value = pool
        api = MagicMock()
        pool.get_api.return_value = api
        api.get_resource.return_value.get.return_value = []
        router_services_fetch_telemetry(
            '192.168.56.20',
            username='telemetry-test-user',
            password='telemetry-test-password',
        )
        _, kwargs = mock_cls.call_args
        self.assertTrue(kwargs.get('plaintext_login'), 'plaintext_login must be True for RouterOS v7')

    @patch(_SERVICES_AVAIL_PATH, True)
    @patch(_SERVICES_POOL_PATH)
    def test_communication_error_returns_auth_fallback(self, mock_cls):
        pool = MagicMock()
        mock_cls.return_value = pool
        pool.get_api.side_effect = RouterOsApiCommunicationError('auth failed', 'auth failed')

        with self.assertLogs('apps.routers.services', level='WARNING') as cm:
            data = router_services_fetch_telemetry(
                '192.168.56.20',
                username='telemetry-test-user',
                password='telemetry-test-password',
            )

        self.assertEqual(data['status'], 'offline')
        self.assertEqual(data.get('detail'), 'Authentication or protocol error')
        self.assertTrue(any('[Telemetry Auth Error] Router 192.168.56.20' in log for log in cm.output))
        pool.disconnect.assert_called_once()

    @patch(_SERVICES_AVAIL_PATH, True)
    @patch(_SERVICES_POOL_PATH)
    def test_socket_timeout_returns_offline_with_error(self, mock_cls):
        pool = MagicMock()
        mock_cls.return_value = pool
        pool.get_api.side_effect = socket.timeout('timed out')

        with self.assertLogs('apps.routers.services', level='WARNING') as cm:
            data = router_services_fetch_telemetry(
                '192.168.56.20',
                username='telemetry-test-user',
                password='telemetry-test-password',
            )

        self.assertEqual(data['status'], 'offline')
        self.assertIn('error', data)
        self.assertTrue(any('[Telemetry Warning] Router 192.168.56.20 unreachable (timed out)' in log for log in cm.output))
        pool.disconnect.assert_called_once()
