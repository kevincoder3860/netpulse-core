from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.operations.models import Customer
from apps.operations.views import ActiveSessionListView, CustomerViewSet
from apps.radius.models import RadAcct
from apps.routers.models import NAS
from apps.tenants.models import Tenant, TenantUser
from apps.vouchers.models import Recharge


class ActiveSessionListViewTests(TestCase):
    databases = {'default', 'radius_db'}

    def setUp(self):
        self.tenant = Tenant.objects.create(
            business_name='Accounting Fallback Cafe',
            email='accounting-fallback@example.com',
            phone_number='+254700000004',
        )
        NAS.objects.create(
            tenant=self.tenant,
            nasname='Fallback Router',
            shortname='Fallback Cafe',
            nas_ip='192.0.2.20',
            secret='radius-secret',
        )
        self.user = get_user_model().objects.create_superuser(
            username='session-fallback-admin',
            email='session-fallback@example.com',
            password='A-Strong-Password-123!',
        )

    def test_missing_radacct_table_returns_empty_list(self):
        request = APIRequestFactory().get('/api/v1/sessions/active/')
        force_authenticate(request, user=self.user)

        with patch.object(ActiveSessionListView, 'get_permissions', return_value=[]):
            response = ActiveSessionListView.as_view()(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, [])

    def test_expired_subscriber_accounting_rows_are_not_reported_as_active(self):
        now = timezone.now()
        Customer.objects.create(
            tenant=self.tenant,
            username='expired-subscriber',
            name='Expired Subscriber',
            phone_number='+254700000005',
            mac_address='02:00:00:00:00:05',
            status=Customer.Status.ACTIVE,
            expires_at=now - timedelta(minutes=1),
        )
        Customer.objects.create(
            tenant=self.tenant,
            username='active-subscriber',
            name='Active Subscriber',
            phone_number='+254700000006',
            mac_address='02:00:00:00:00:06',
            status=Customer.Status.ACTIVE,
            expires_at=now + timedelta(minutes=30),
        )
        RadAcct.objects.using('radius_db').bulk_create([
            RadAcct(
                acctsessionid='expired-session',
                acctuniqueid='expired-session-unique',
                username='expired-subscriber',
                nasipaddress='192.0.2.20',
                acctstarttime=now - timedelta(minutes=30),
                callingstationid='02:00:00:00:00:05',
            ),
            RadAcct(
                acctsessionid='active-session',
                acctuniqueid='active-session-unique',
                username='active-subscriber',
                nasipaddress='192.0.2.20',
                acctstarttime=now - timedelta(minutes=2),
                callingstationid='02:00:00:00:00:06',
            ),
        ])

        request = APIRequestFactory().get(
            '/api/v1/sessions/active/',
            {'tenant_id': str(self.tenant.id)},
        )
        force_authenticate(request, user=self.user)
        with patch.object(ActiveSessionListView, 'get_permissions', return_value=[]):
            response = ActiveSessionListView.as_view()(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual([row['username'] for row in response.data], ['active-subscriber'])


class CustomerStatusLifecycleTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            business_name='Subscriber Status ISP',
            email='subscriber-status@example.com',
            phone_number='+254700000007',
        )
        self.user = get_user_model().objects.create_user(
            username='subscriber-status-vendor',
            password='A-Strong-Password-123!',
        )
        TenantUser.objects.create(
            user=self.user,
            tenant=self.tenant,
            role=TenantUser.Role.VENDOR,
        )

    def test_customer_list_activates_paid_pending_and_expires_elapsed_profiles(self):
        now = timezone.now()
        pending_customer = Customer.objects.create(
            tenant=self.tenant,
            username='paid-pending-subscriber',
            name='Paid Pending Subscriber',
            phone_number='+254700000008',
            status='pending',
            expires_at=now - timedelta(hours=1),
        )
        Recharge.objects.create(
            tenant=self.tenant,
            username=pending_customer.username,
            expires_at=now + timedelta(minutes=30),
        )
        expired_customer = Customer.objects.create(
            tenant=self.tenant,
            username='elapsed-subscriber',
            name='Elapsed Subscriber',
            phone_number='+254700000009',
            status=Customer.Status.ACTIVE,
            expires_at=now - timedelta(minutes=1),
        )

        request = APIRequestFactory().get(
            '/api/v1/customers/',
            {'tenant_id': str(self.tenant.id)},
        )
        force_authenticate(request, user=self.user)
        response = CustomerViewSet.as_view({'get': 'list'})(request)

        self.assertEqual(response.status_code, 200)
        statuses = {row['username']: row['status'] for row in response.data}
        self.assertEqual(statuses[pending_customer.username], Customer.Status.ACTIVE)
        self.assertEqual(statuses[expired_customer.username], Customer.Status.EXPIRED)
        pending_customer.refresh_from_db()
        expired_customer.refresh_from_db()
        self.assertEqual(pending_customer.status, Customer.Status.ACTIVE)
        self.assertEqual(pending_customer.expires_at, now + timedelta(minutes=30))
        self.assertEqual(expired_customer.status, Customer.Status.EXPIRED)
