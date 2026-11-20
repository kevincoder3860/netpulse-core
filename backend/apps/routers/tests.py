import socket
from cryptography.fernet import Fernet
from django.conf import settings
from django.db import OperationalError
from django.test import TestCase
from django.db import connections
from django.contrib.auth import get_user_model
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from rest_framework.test import APIRequestFactory, force_authenticate
from apps.routers.views import RouterViewSet
from apps.routers.models import NAS
from apps.routers.serializers import NASSerializer
from apps.routers.tasks import _check_single_router
from apps.tenants.models import Tenant, TenantUser
from apps.routers.services import RouterConnectionError, _command_words_with_id, _credential_value, _is_nonfatal_routeros_trap, _read_print_records, build_mikrotik_provisioning_commands, check_router_status, fetch_router_metrics, fetch_router_telemetry, resolve_radius_address, resolve_router_credentials, sync_radius_nas_record
from librouteros.exceptions import TrapError


class InlineExecutor:
    def __init__(self, max_workers=None):
        self.max_workers = max_workers

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def map(self, function, iterable):
        return map(function, iterable)


class RouterProvisioningServiceTests(TestCase):
    databases = {'default', 'radius_db'}

    def setUp(self):
        super().setUp()
        with connections['radius_db'].cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS nas (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nasname VARCHAR(128) NOT NULL,
                    shortname VARCHAR(32),
                    type VARCHAR(30) DEFAULT 'other',
                    ports INTEGER,
                    secret VARCHAR(60) NOT NULL,
                    server VARCHAR(64),
                    community VARCHAR(50),
                    description VARCHAR(200) DEFAULT 'RADIUS Client'
                )
                """
            )

    def test_build_mikrotik_provisioning_commands_includes_required_steps(self):
        commands = build_mikrotik_provisioning_commands(
            router_name='MT-CAFE-03',
            radius_server_ip='10.10.0.5',
            shared_secret='NetPulseSecret',
        )

        self.assertIn('/system/identity/set', commands[0])
        self.assertIn('=name=MT-CAFE-03', commands[0])
        self.assertIn('/radius/add', commands[1])
        self.assertIn('=address=10.10.0.5', commands[1])
        self.assertIn('=secret=NetPulseSecret', commands[1])
        self.assertIn('=accept=yes', commands[2])
        self.assertIn('=use-radius=yes', commands[3])
        self.assertIn('=shared-users=1', commands[4])
        self.assertIn('*.m-pesa.co.ke', ''.join(commands))

    def test_duplicate_routeros_traps_are_nonfatal(self):
        self.assertTrue(_is_nonfatal_routeros_trap('failure: already have such entry'))
        self.assertTrue(_is_nonfatal_routeros_trap('cannot modify item'))
        self.assertFalse(_is_nonfatal_routeros_trap('not enough permissions'))

    def test_routeros_set_commands_resolve_ids_or_fallback_to_add(self):
        with patch('apps.routers.services._read_print_records', return_value=[{'.id': '*7', 'default': 'yes'}]):
            words, _ = _command_words_with_id(
                object(),
                '/ip/hotspot/profile/set [ find default=yes ] =use-radius=yes',
            )
        self.assertIn(b'=.id=*7', words)
        self.assertIn(b'=use-radius=yes', words)

        with patch('apps.routers.services._read_print_records', return_value=[]):
            words, _ = _command_words_with_id(
                object(),
                '/radius/incoming/set =accept=yes',
            )
        self.assertEqual(words[0], b'/radius/incoming/add')

    def test_routeros_print_uses_dotted_proplist_attribute(self):
        sock = SimpleNamespace()
        sent = []
        with patch('apps.routers.services.send_sentence', side_effect=lambda _sock, words: sent.append(words)), patch('apps.routers.services.read_sentence', return_value=[b'!done']):
            self.assertEqual(_read_print_records(sock, '/radius'), [])
        self.assertIn(b'=.proplist=.id,name,default', sent[0])

    def test_router_credentials_prefer_request_and_fallback_to_plaintext(self):
        router = SimpleNamespace(api_username='stored_user', api_password='stored_password')
        self.assertEqual(resolve_router_credentials(router, 'request_user', 'request_password'), ('request_user', 'request_password'))
        with patch.dict('os.environ', {'CREDENTIAL_ENCRYPTION_KEY': 'invalid-key'}):
            self.assertEqual(_credential_value('plain_password'), 'plain_password')

    def test_router_credentials_without_encryption_key_fall_back_to_plaintext(self):
        router = SimpleNamespace(api_username='stored_user', api_password='stored_password')
        with patch.dict('os.environ', {}, clear=True):
            self.assertEqual(
                resolve_router_credentials(router),
                ('stored_user', 'stored_password'),
            )

    def test_plaintext_router_credentials_do_not_warn_on_each_read(self):
        with (
            patch.dict('os.environ', {}, clear=True),
            self.assertNoLogs('apps.routers.services', level='WARNING'),
        ):
            self.assertEqual(_credential_value('legacy-plaintext-password'), 'legacy-plaintext-password')

    def test_test_encryption_key_decrypts_router_credentials_when_env_key_is_unset(self):
        encrypted = Fernet(settings.CREDENTIAL_ENCRYPTION_KEY.encode()).encrypt(
            b'secret-router-password'
        ).decode()
        with patch.dict('os.environ', {}, clear=True):
            self.assertEqual(_credential_value(encrypted), 'secret-router-password')

    def test_radius_address_aliases_are_resolved_and_validated(self):
        self.assertEqual(resolve_radius_address(radius_server_ip='10.10.0.5'), '10.10.0.5')
        self.assertEqual(resolve_radius_address(radius_ip='10.10.0.6', address='10.10.0.7'), '10.10.0.6')
        self.assertEqual(resolve_radius_address(address='10.10.0.7'), '10.10.0.7')
        with self.assertRaisesRegex(Exception, 'RADIUS address is required'):
            resolve_radius_address()

    def test_provision_view_connects_with_stored_router_settings(self):
        tenant = Tenant.objects.create(
            business_name='Provision Cafe',
            email='provision-cafe@example.com',
            phone_number='+254700000001',
        )
        router = NAS.objects.create(
            tenant=tenant,
            nasname='Provision Router',
            shortname='Provision Cafe',
            nas_ip='192.168.56.101',
            secret='radius-secret',
            api_port=8728,
            api_username='admin',
            api_password='password',
        )
        factory = APIRequestFactory()
        request = factory.post(f'/api/v1/routers/{router.pk}/provision/', {}, format='json')
        connection = MagicMock()
        with (
            patch.object(RouterViewSet, 'get_permissions', return_value=[]),
            patch.object(RouterViewSet, 'get_object', return_value=router),
            patch('librouteros.connect', return_value=connection) as connect,
        ):
            response = RouterViewSet.as_view({'post': 'provision'})(request, pk=router.pk)

        self.assertEqual(response.status_code, 200, getattr(response, 'data', response))
        self.assertEqual(connect.call_args.kwargs['host'], '192.168.56.101')
        self.assertEqual(connect.call_args.kwargs['timeout'], 5.0)
        connection.close.assert_called_once()

    def test_sync_radius_nas_record_creates_or_updates_record(self):
        result = sync_radius_nas_record(
            nasname='MT-CAFE-03',
            shortname='Main Cafe',
            secret='NetPulseSecret',
            router_type='mikrotik',
        )

        self.assertTrue(result['created'] or result['updated'])
        self.assertEqual(result['nasname'], 'MT-CAFE-03')
        self.assertEqual(result['secret'], 'NetPulseSecret')

    def test_router_serializer_updates_existing_nasname(self):
        tenant = Tenant.objects.create(
            business_name='Main Cafe',
            email='main-cafe@example.com',
            phone_number='+254700000000',
        )
        payload = {
            'tenant': str(tenant.id),
            'nasname': '192.168.56.101',
            'shortname': 'Main Cafe',
            'nas_ip': '192.168.56.101',
            'secret': 'first-secret',
            'api_port': 8728,
            'api_username': 'admin',
            'api_password': 'first-password',
            'radius_server_ip': '10.10.0.5',
            'shared_secret': 'first-secret',
            'type': 'mikrotik',
        }
        first = NASSerializer(data=payload)
        self.assertTrue(first.is_valid(), first.errors)
        first_router = first.save()

        payload.update({'shortname': 'Updated Cafe', 'secret': 'updated-secret'})
        second = NASSerializer(data=payload)
        self.assertTrue(second.is_valid(), second.errors)
        second_router = second.save()

        self.assertEqual(first_router.pk, second_router.pk)
        second_router.refresh_from_db()
        self.assertEqual(second_router.shortname, 'Updated Cafe')
        self.assertEqual(second_router.secret, 'updated-secret')

    def test_router_update_saves_changes_without_connectivity_check(self):
        tenant = Tenant.objects.create(
            business_name='Ping Cafe',
            email='ping-cafe@example.com',
            phone_number='+254700000002',
        )
        router = NAS.objects.create(
            tenant=tenant,
            nasname='Ping Router',
            shortname='Ping Cafe',
            nas_ip='192.168.56.101',
            secret='radius-secret',
        )
        request = APIRequestFactory().patch(
            f'/api/v1/routers/{router.pk}/',
            {
                'api_ip': '192.168.56.20',
                'nasname': 'Updated Router',
                'shortname': 'Updated Cafe',
                'api_port': 8729,
                'api_username': 'netpulse_admin',
                'api_password': 'updated-password',
            },
            format='json',
        )
        with patch.object(RouterViewSet, 'get_permissions', return_value=[]), patch.object(RouterViewSet, 'get_object', return_value=router):
            response = RouterViewSet.as_view({'patch': 'partial_update'})(request, pk=router.pk)

        self.assertEqual(response.status_code, 200, getattr(response, 'data', response))
        router.refresh_from_db()
        self.assertEqual(router.nas_ip, '192.168.56.20')
        self.assertEqual(router.nasname, 'Updated Router')
        self.assertEqual(router.shortname, 'Updated Cafe')
        self.assertEqual(router.api_port, 8729)
        self.assertEqual(router.api_username, 'netpulse_admin')
        self.assertEqual(router.api_password, 'updated-password')
        self.assertFalse(router.is_online)
        self.assertEqual(router.status, 'offline')
        self.assertIsNone(router.last_ping)
        self.assertEqual(router.tenant_id, tenant.id)

    def test_router_update_rejects_invalid_ip_without_saving(self):
        tenant = Tenant.objects.create(
            business_name='IP Validation Cafe',
            email='ip-validation-cafe@example.com',
            phone_number='+254700000003',
        )
        router = NAS.objects.create(
            tenant=tenant,
            nasname='Validation Router',
            shortname='Validation Cafe',
            nas_ip='192.168.56.10',
            secret='radius-secret',
        )
        request = APIRequestFactory().patch(
            f'/api/v1/routers/{router.pk}/',
            {'nas_ip': 'not-an-ip'},
            format='json',
        )
        with patch.object(RouterViewSet, 'get_permissions', return_value=[]), patch.object(RouterViewSet, 'get_object', return_value=router):
            response = RouterViewSet.as_view({'patch': 'partial_update'})(request, pk=router.pk)

        self.assertEqual(response.status_code, 400)
        router.refresh_from_db()
        self.assertEqual(router.nas_ip, '192.168.56.10')

    def test_router_delete_removes_router(self):
        tenant = Tenant.objects.create(
            business_name='Delete Cafe',
            email='delete-cafe@example.com',
            phone_number='+254700000004',
        )
        router = NAS.objects.create(
            tenant=tenant,
            nasname='Delete Router',
            shortname='Delete Cafe',
            secret='radius-secret',
        )
        request = APIRequestFactory().delete(f'/api/v1/routers/{router.pk}/')
        with patch.object(RouterViewSet, 'get_permissions', return_value=[]), patch.object(RouterViewSet, 'get_object', return_value=router):
            response = RouterViewSet.as_view({'delete': 'destroy'})(request, pk=router.pk)

        self.assertEqual(response.status_code, 204)
        self.assertFalse(NAS.objects.filter(pk=router.pk).exists())

    def test_router_health_check_preserves_tenant_when_it_connects(self):
        tenant = Tenant.objects.create(
            business_name='Health Persistence Cafe',
            email='health-persistence-cafe@example.com',
            phone_number='+254700000018',
        )
        router = NAS.objects.create(
            tenant=tenant,
            nasname='Health Persistence Router',
            shortname='Health Persistence',
            nas_ip='192.0.2.41',
            secret='radius-secret',
            api_username='admin',
            api_password='password',
            is_online=False,
            status='offline',
        )
        connection = MagicMock()

        with patch('apps.routers.services.librouteros_connect', return_value=connection):
            result = check_router_status(router)

        router.refresh_from_db()
        self.assertTrue(result['is_online'])
        self.assertTrue(router.is_online)
        self.assertEqual(router.status, 'online')
        self.assertEqual(router.tenant_id, tenant.id)

    def test_router_health_status_write_handles_sqlite_lock(self):
        tenant = Tenant.objects.create(
            business_name='Locked Health Cafe',
            email='locked-health@example.com',
            phone_number='+254700000019',
        )
        router = NAS.objects.create(
            tenant=tenant,
            nasname='Locked Health Router',
            shortname='Locked Health',
            nas_ip='192.0.2.42',
            secret='radius-secret',
            api_username='admin',
            api_password='password',
            is_online=False,
            status='offline',
        )

        with (
            patch('apps.routers.services.librouteros_connect', return_value=MagicMock()),
            patch.object(router, 'save', side_effect=OperationalError('database is locked')),
            self.assertLogs('apps.routers.services', level='WARNING'),
        ):
            result = check_router_status(router)

        self.assertFalse(result['is_online'])
        self.assertEqual(result['status'], 'offline')
        self.assertFalse(router.is_online)
        self.assertEqual(router.status, 'offline')

    def test_router_list_returns_service_unavailable_when_database_is_locked(self):
        request = APIRequestFactory().get('/api/v1/routers/')
        with (
            patch.object(RouterViewSet, 'get_permissions', return_value=[]),
            patch.object(
                RouterViewSet,
                'filter_queryset',
                side_effect=OperationalError('database is locked'),
            ),
        ):
            response = RouterViewSet.as_view({'get': 'list'})(request)

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data['code'], 'DATABASE_BUSY')

    def test_router_health_task_logs_unreachable_router_without_raising(self):
        router = SimpleNamespace(pk=17, nas_ip='192.0.2.41', nasname='Offline Router')

        with (
            patch('apps.routers.tasks.check_router_status', side_effect=socket.timeout('timed out')),
            self.assertLogs('apps.routers.tasks', level='WARNING') as logs,
        ):
            result = _check_single_router(router)

        self.assertEqual(result['status'], 'offline')
        self.assertFalse(result['is_online'])
        self.assertEqual(result['error'], 'timed out')
        self.assertIn('Router health check could not reach NAS 17 (192.0.2.41)', logs.output[0])

    def test_vendor_router_list_is_scoped_to_authenticated_tenant(self):
        tenant = Tenant.objects.create(
            business_name='Assigned Cafe',
            email='assigned-cafe@example.com',
            phone_number='+254700000010',
        )
        other_tenant = Tenant.objects.create(
            business_name='Other Cafe',
            email='other-cafe@example.com',
            phone_number='+254700000011',
        )
        assigned_router = NAS.objects.create(
            tenant=tenant,
            nasname='Shared Router Name',
            shortname='Assigned',
            secret='radius-secret',
        )
        NAS.objects.create(
            tenant=other_tenant,
            nasname='Other Router',
            shortname='Other',
            secret='radius-secret',
        )
        user = get_user_model().objects.create_user(
            username='assigned-vendor',
            password='test-password',
        )
        TenantUser.objects.create(
            user=user,
            tenant=tenant,
            role=TenantUser.Role.VENDOR,
        )
        request = APIRequestFactory().get(
            f'/api/v1/routers/?tenant_id={other_tenant.id}'
        )
        force_authenticate(request, user=user)

        response = RouterViewSet.as_view({'get': 'list'})(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual([router['id'] for router in response.data], [assigned_router.id])
        self.assertEqual(response.data[0]['tenant'], tenant.id)
        assigned_router.refresh_from_db()
        self.assertIsNone(assigned_router.last_ping)

    def test_vendor_router_creation_uses_authenticated_tenant(self):
        tenant = Tenant.objects.create(
            business_name='Authenticated Cafe',
            email='authenticated-cafe@example.com',
            phone_number='+254700000016',
        )
        other_tenant = Tenant.objects.create(
            business_name='Submitted Cafe',
            email='submitted-cafe@example.com',
            phone_number='+254700000017',
        )
        user = get_user_model().objects.create_user(
            username='authenticated-vendor',
            password='test-password',
        )
        TenantUser.objects.create(
            user=user,
            tenant=tenant,
            role=TenantUser.Role.VENDOR,
        )
        request = APIRequestFactory().post(
            '/api/v1/routers/',
            {
                'tenant': str(other_tenant.id),
                'nasname': 'Vendor-owned Router',
                'shortname': 'Authenticated',
                'nas_ip': '192.0.2.40',
                'secret': 'radius-secret',
            },
            format='json',
        )
        force_authenticate(request, user=user)

        response = RouterViewSet.as_view({'post': 'create'})(request)

        self.assertEqual(response.status_code, 201, response.data)
        router = NAS.objects.get(nasname='Vendor-owned Router')
        self.assertEqual(router.tenant_id, tenant.id)
        self.assertEqual(response.data['tenant'], tenant.id)

    def test_router_create_rejects_invalid_ip_without_creating_router(self):
        tenant = Tenant.objects.create(
            business_name='Invalid IP Cafe',
            email='invalid-ip-cafe@example.com',
            phone_number='+254700000018',
        )
        request = APIRequestFactory().post(
            '/api/v1/routers/',
            {
                'tenant': str(tenant.id),
                'nasname': 'Invalid IP Router',
                'shortname': 'Invalid IP Cafe',
                'nas_ip': 'not-an-ip',
                'secret': 'radius-secret',
            },
            format='json',
        )
        with patch.object(RouterViewSet, 'get_permissions', return_value=[]):
            response = RouterViewSet.as_view({'post': 'create'})(request)

        self.assertEqual(response.status_code, 400)
        self.assertFalse(NAS.objects.filter(nasname='Invalid IP Router').exists())

    def test_router_with_same_name_is_created_without_reassigning_another_tenant(self):
        first_tenant = Tenant.objects.create(
            business_name='First Cafe',
            email='first-cafe@example.com',
            phone_number='+254700000012',
        )
        second_tenant = Tenant.objects.create(
            business_name='Second Cafe',
            email='second-cafe@example.com',
            phone_number='+254700000013',
        )
        existing_router = NAS.objects.create(
            tenant=first_tenant,
            nasname='Repeated Router',
            shortname='First',
            secret='first-secret',
        )
        payload = {
            'tenant': str(second_tenant.id),
            'nasname': 'Repeated Router',
            'shortname': 'Second',
            'secret': 'second-secret',
        }

        serializer = NASSerializer(data=payload)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        created_router = serializer.save()

        self.assertNotEqual(created_router.pk, existing_router.pk)
        existing_router.refresh_from_db()
        self.assertEqual(existing_router.tenant_id, first_tenant.id)
        self.assertEqual(created_router.tenant_id, second_tenant.id)
        self.assertEqual(NAS.objects.filter(nasname='Repeated Router').count(), 2)

    def test_router_status_update_cannot_reassign_its_tenant(self):
        tenant = Tenant.objects.create(
            business_name='Router Owner',
            email='router-owner@example.com',
            phone_number='+254700000014',
        )
        other_tenant = Tenant.objects.create(
            business_name='Unexpected Owner',
            email='unexpected-owner@example.com',
            phone_number='+254700000015',
        )
        router = NAS.objects.create(
            tenant=tenant,
            nasname='Owned Router',
            shortname='Owned',
            secret='radius-secret',
        )
        serializer = NASSerializer(
            router,
            data={'tenant': str(other_tenant.id), 'status': 'online'},
            partial=True,
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn('tenant', serializer.errors)
        router.refresh_from_db()
        self.assertEqual(router.tenant_id, tenant.id)

    def test_list_checks_router_reachability_and_persists_status(self):
        tenant = Tenant.objects.create(
            business_name='Health Check Cafe',
            email='health-check-cafe@example.com',
            phone_number='+254700000005',
        )
        online_router = NAS.objects.create(
            tenant=tenant,
            nasname='Online Router',
            shortname='Online',
            nas_ip='192.0.2.21',
            secret='radius-secret',
            api_username='admin',
            api_password='password',
            is_online=False,
            status='offline',
        )
        offline_router = NAS.objects.create(
            tenant=tenant,
            nasname='Offline Router',
            shortname='Offline',
            nas_ip='192.0.2.22',
            api_port=8729,
            secret='radius-secret',
            api_username='admin',
            api_password='password',
            is_online=True,
            status='online',
        )
        user = SimpleNamespace(is_superuser=True, is_authenticated=True)
        request = APIRequestFactory().get('/api/v1/routers/')
        force_authenticate(request, user=user)

        def fake_routeros_connection(host, **_kwargs):
            if host == online_router.nas_ip:
                return MagicMock()
            raise socket.timeout('timed out')

        with (
            patch.object(RouterViewSet, 'get_permissions', return_value=[]),
            patch('apps.routers.views.ThreadPoolExecutor', InlineExecutor),
            patch('apps.routers.services.librouteros_connect', side_effect=fake_routeros_connection),
        ):
            response = RouterViewSet.as_view({'get': 'list'})(request)

        self.assertEqual(response.status_code, 200)
        statuses = {str(item['id']): item['is_online'] for item in response.data}
        self.assertTrue(statuses[str(online_router.pk)])
        self.assertFalse(statuses[str(offline_router.pk)])
        online_router.refresh_from_db()
        offline_router.refresh_from_db()
        self.assertTrue(online_router.is_online)
        self.assertEqual(online_router.status, 'online')
        self.assertIsNotNone(online_router.last_ping)
        self.assertEqual(online_router.tenant_id, tenant.id)
        self.assertFalse(offline_router.is_online)
        self.assertEqual(offline_router.status, 'offline')

        stable_request = APIRequestFactory().get('/api/v1/routers/')
        force_authenticate(stable_request, user=user)
        with (
            patch.object(RouterViewSet, 'get_permissions', return_value=[]),
            patch('apps.routers.views.ThreadPoolExecutor', InlineExecutor),
            patch('apps.routers.services.librouteros_connect', side_effect=fake_routeros_connection),
        ):
            stable_response = RouterViewSet.as_view({'get': 'list'})(stable_request)

        self.assertEqual(stable_response.status_code, 200)
        self.assertEqual(stable_response.data[0]['tenant'], tenant.id)

    def test_metrics_action_returns_router_specific_metrics(self):
        tenant = Tenant.objects.create(
            business_name='Metrics Cafe',
            email='metrics-cafe@example.com',
            phone_number='+254700000006',
        )
        router = NAS.objects.create(
            tenant=tenant,
            nasname='Metrics Router',
            shortname='Metrics',
            nas_ip='192.0.2.23',
            secret='radius-secret',
        )
        request = APIRequestFactory().get(f'/api/v1/routers/{router.pk}/metrics/')
        force_authenticate(request, user=SimpleNamespace(is_superadmin=True, is_authenticated=True))
        metrics = {
            'router_id': str(router.pk),
            'ip_address': router.nas_ip,
            'cpu_usage_percent': 12.0,
            'memory_used_bytes': 512,
            'memory_total_bytes': 1024,
            'memory_usage_percent': 50.0,
            'uptime': '1d00:00:00',
            'interfaces': [{'name': 'ether1', 'rx_bytes': 100, 'tx_bytes': 200}],
            'active_hotspot_users': 3,
            'captured_at': '2026-10-27T00:00:00+00:00',
        }

        with (
            patch.object(RouterViewSet, 'get_permissions', return_value=[]),
            patch.object(RouterViewSet, 'get_object', return_value=router),
            patch('apps.routers.views.fetch_router_metrics', return_value=metrics) as fetch_metrics,
        ):
            response = RouterViewSet.as_view({'get': 'metrics'})(request, pk=router.pk)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, metrics)
        fetch_metrics.assert_called_once_with(router)

    def test_fetch_router_metrics_reads_resource_interfaces_and_active_users(self):
        router = SimpleNamespace(
            pk=7,
            nas_ip='192.0.2.24',
            api_port=8729,
            api_username='metrics-user',
            api_password='metrics-password',
        )
        connection = MagicMock()
        resource_query = MagicMock()
        interface_query = MagicMock()
        active_query = MagicMock()
        paths = {
            ('system', 'resource'): resource_query,
            ('interface',): interface_query,
            ('ip', 'hotspot', 'active'): active_query,
        }
        connection.path.side_effect = lambda *path: paths[path]
        resource_query.return_value.__iter__.return_value = iter([{
            'cpu-load': '23',
            'total-memory': '1024',
            'free-memory': '256',
            'uptime': '2d03:04:05',
        }])
        interface_query.return_value.__iter__.return_value = iter([
            {'name': 'ether1', 'rx-byte': '1200', 'tx-byte': '3400'},
        ])
        active_query.return_value.__iter__.return_value = iter([
            {'.id': '*1'},
            {'.id': '*2'},
        ])

        with (
            patch('apps.routers.services.resolve_router_credentials', return_value=('metrics-user', 'metrics-password')),
            patch('apps.routers.services.librouteros_connect', return_value=connection) as connect,
        ):
            result = fetch_router_metrics(router)

        connect.assert_called_once_with(
            host=str(router.nas_ip),
            username='metrics-user',
            password='metrics-password',
            port=int(router.api_port or 8728),
            timeout=5,
        )
        self.assertEqual(result['cpu_usage_percent'], 23.0)
        self.assertEqual(result['memory_used_bytes'], 768)
        self.assertEqual(result['memory_free_bytes'], 256)
        self.assertEqual(result['memory_usage_percent'], 75.0)
        self.assertEqual(result['uptime'], '2d03:04:05')
        self.assertEqual(result['interfaces'], [{'name': 'ether1', 'rx_bytes': 1200, 'tx_bytes': 3400}])
        self.assertEqual(result['active_hotspot_users'], 2)
        resource_query.assert_called_once_with('print')
        interface_query.assert_called_once_with('print')
        active_query.assert_called_once_with('print')
        connection.close.assert_called_once()

    def test_fetch_router_metrics_uses_plaintext_credentials_without_encryption_key(self):
        router = SimpleNamespace(
            pk=8,
            nas_ip='192.0.2.25',
            api_port=None,
            api_username='plain-user',
            api_password='plain-password',
        )
        connection = MagicMock()
        connection.path.return_value.return_value.__iter__.return_value = iter([{
            'cpu-load': 1,
            'total-memory': 100,
            'free-memory': 50,
            'uptime': '00:01:00',
        }])

        with (
            patch.dict('os.environ', {}, clear=True),
            patch('apps.routers.services.librouteros_connect', return_value=connection) as connect,
            patch('apps.routers.services.logger.warning'),
        ):
            result = fetch_router_metrics(router)

        self.assertEqual(result['router_id'], '8')
        self.assertEqual(result['memory_free_bytes'], 50)
        self.assertEqual(connection.path.return_value.call_args.args, ('print',))
        connect.assert_called_once_with(
            host='192.0.2.25',
            username='plain-user',
            password='plain-password',
            port=8728,
            timeout=5,
        )
        connection.close.assert_called_once()

    def test_librouteros_telemetry_fallback_invokes_query_and_reads_system_resources(self):
        connection = MagicMock()
        path_queries = {
            'interface': MagicMock(),
            'system_resource': MagicMock(),
        }
        path_queries['interface'].return_value.__iter__.return_value = iter([
            {'name': 'ether1', 'rx-byte': '120', 'tx-byte': '240'},
        ])
        path_queries['system_resource'].return_value.__iter__.return_value = iter([{
            'cpu-load': '17',
            'total-memory': '1000',
            'free-memory': '400',
            'uptime': '3d04:05:06',
        }])
        connection.path.side_effect = lambda *path: path_queries[
            'system_resource' if path == ('system', 'resource') else path[0]
        ]

        with (
            patch('apps.routers.services._ROUTEROS_API_AVAILABLE', False),
            patch('apps.routers.services.librouteros_connect', return_value=connection),
        ):
            result = fetch_router_telemetry(
                '192.0.2.27',
                username='metrics-user',
                password='metrics-password',
            )

        self.assertEqual(result['status'], 'online')
        self.assertEqual(result['cpu'], 17.0)
        self.assertEqual(result['memory'], 60.0)
        self.assertEqual(result['free_memory_bytes'], 400)
        self.assertEqual(result['uptime'], '3d04:05:06')
        self.assertEqual(result['interface'], 'ether1')
        connection.path.assert_any_call('system', 'resource')
        connection.path.assert_any_call('interface')
        path_queries['system_resource'].assert_called_once_with('print')
        path_queries['interface'].assert_called_once_with('print')
        connection.close.assert_called_once()

    def test_fetch_router_metrics_logs_exact_routeros_exception_details(self):
        router = SimpleNamespace(
            pk=10,
            nas_ip='192.0.2.26',
            api_port=8728,
            api_username='metrics-user',
            api_password='metrics-password',
        )
        routeros_error = TrapError('permission denied')

        with (
            patch('apps.routers.services.resolve_router_credentials', return_value=('metrics-user', 'metrics-password')),
            patch('apps.routers.services.librouteros_connect', side_effect=routeros_error),
            self.assertLogs('apps.routers.services', level='ERROR') as captured_logs,
        ):
            with self.assertRaises(RouterConnectionError) as raised:
                fetch_router_metrics(router)

        self.assertEqual(raised.exception.code, 'ROUTEROS_API_ERROR')
        self.assertTrue(any(
            'TrapError: permission denied' in log
            and 'router 10 (192.0.2.26)' in log
            for log in captured_logs.output
        ))

    def test_metrics_action_returns_structured_response_for_unexpected_errors(self):
        router = SimpleNamespace(pk=9)
        request = APIRequestFactory().get('/api/v1/routers/9/metrics/')
        force_authenticate(request, user=SimpleNamespace(is_superadmin=True, is_authenticated=True))

        with (
            patch.object(RouterViewSet, 'get_permissions', return_value=[]),
            patch.object(RouterViewSet, 'get_object', return_value=router),
            patch('apps.routers.views.fetch_router_metrics', side_effect=RuntimeError('unexpected details')),
        ):
            response = RouterViewSet.as_view({'get': 'metrics'})(request, pk=9)

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.data, {
            'detail': 'Unable to retrieve live metrics from the router.',
            'code': 'ROUTER_METRICS_FAILED',
        })

    def test_provision_view_returns_structured_timeout_response(self):
        tenant = Tenant.objects.create(
            business_name='Timeout Cafe',
            email='timeout-cafe@example.com',
            phone_number='+254700000003',
        )
        router = NAS.objects.create(
            tenant=tenant,
            nasname='Timeout Router',
            shortname='Timeout Cafe',
            nas_ip='192.0.2.10',
            secret='radius-secret',
            api_port=8728,
            api_username='admin',
            api_password='router-password',
        )
        request = APIRequestFactory().post(
            f'/api/v1/routers/{router.pk}/provision/',
            {},
            format='json',
        )
        with (
            patch.object(RouterViewSet, 'get_permissions', return_value=[]),
            patch.object(RouterViewSet, 'get_object', return_value=router),
            patch('librouteros.connect', side_effect=socket.timeout('timed out')),
        ):
            response = RouterViewSet.as_view({'post': 'provision'})(request, pk=router.pk)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['code'], 'ROUTER_CONNECTION_TIMEOUT')
        self.assertEqual(
            response.data['message'],
            'Router connection timed out. Please check IP and port.',
        )
        self.assertFalse(response.data['is_online'])
