from django.test import TestCase
from django.db import connections
from types import SimpleNamespace
from unittest.mock import patch
from rest_framework.test import APIRequestFactory
from apps.routers.views import RouterViewSet
from apps.routers.models import NAS
from apps.routers.serializers import NASSerializer
from apps.tenants.models import Tenant
from apps.routers.services import _command_words_with_id, _credential_value, _is_nonfatal_routeros_trap, _read_print_records, build_mikrotik_provisioning_commands, resolve_radius_address, resolve_router_credentials, sync_radius_nas_record


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

    def test_radius_address_aliases_are_resolved_and_validated(self):
        self.assertEqual(resolve_radius_address(radius_server_ip='10.10.0.5'), '10.10.0.5')
        self.assertEqual(resolve_radius_address(radius_ip='10.10.0.6', address='10.10.0.7'), '10.10.0.6')
        self.assertEqual(resolve_radius_address(address='10.10.0.7'), '10.10.0.7')
        with self.assertRaisesRegex(Exception, 'RADIUS address is required'):
            resolve_radius_address()

    def test_provision_view_uses_default_radius_address(self):
        factory = APIRequestFactory()
        request = factory.post('/api/v1/routers/1/provision/', {}, format='json')
        with patch.object(RouterViewSet, 'get_permissions', return_value=[]), patch.object(RouterViewSet, 'get_object') as get_object, patch('apps.routers.views.provision_mikrotik_router') as provision:
            router = type('Router', (), {'id': 1, 'nas_ip': '192.168.56.101', 'nasname': 'Router', 'api_port': 8728, 'api_username': 'admin', 'api_password': 'password', 'radius_server_ip': '', 'shared_secret': 'secret', 'secret': 'secret', 'shortname': 'Cafe'})()
            get_object.return_value = router
            provision.return_value = {'ok': True, 'success': True, 'code': 'OK'}
            response = RouterViewSet.as_view({'post': 'provision'})(request, pk=1)

        self.assertEqual(response.status_code, 200, getattr(response, 'data', response))
        self.assertEqual(provision.call_args.kwargs['radius_ip'], '192.168.56.1')

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

    def test_router_update_pings_and_marks_router_online(self):
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
            {'api_ip': '192.168.56.101', 'api_port': 8728, 'api_username': 'netpulse_admin', 'api_password': '123'},
            format='json',
        )
        with patch.object(RouterViewSet, 'get_permissions', return_value=[]), patch.object(RouterViewSet, 'get_object', return_value=router), patch('apps.routers.views.ping_router_with_credentials', return_value=('192.168.56.101', 8728, 'netpulse_admin', '123')):
            response = RouterViewSet.as_view({'patch': 'partial_update'})(request, pk=router.pk)

        self.assertEqual(response.status_code, 200, getattr(response, 'data', response))
        router.refresh_from_db()
        self.assertTrue(router.is_online)
        self.assertEqual(router.status, 'online')
        self.assertEqual(router.api_username, 'netpulse_admin')
        self.assertEqual(router.api_password, '123')
        self.assertIsNotNone(router.last_ping)
