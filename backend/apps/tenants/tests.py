from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.operations.models import Customer, Invoice, PlatformUser
from apps.tenants.models import Tenant


class VendorAuthenticationTests(APITestCase):
    def test_vendor_registration_returns_tokens_and_hashes_password(self):
        response = self.client.post(
            '/api/v1/auth/register/vendor/',
            {
                'email': 'vendor@example.com',
                'password': 'StrongPassword123!',
                'first_name': 'Ada',
                'last_name': 'Vendor',
                'company_name': 'Ada Hotspots',
                'phone_number': '+254700000000',
            },
            format='json',
        )

        self.assertEqual(response.status_code, 201)
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)
        self.assertEqual(response.data['user']['email'], 'vendor@example.com')
        self.assertEqual(response.data['user']['role'], 'VENDOR')
        self.assertTrue(response.data['user']['is_vendor'])
        self.assertEqual(response.data['tenant']['business_name'], 'Ada Hotspots')

        user = get_user_model().objects.get(email='vendor@example.com')
        self.assertNotEqual(user.password, 'StrongPassword123!')
        self.assertTrue(user.check_password('StrongPassword123!'))
        self.assertEqual(user.first_name, 'Ada')
        self.assertEqual(user.last_name, 'Vendor')
        self.assertEqual(str(user.tenant_profile.tenant_id), response.data['tenant']['id'])

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")
        self.assertEqual(
            self.client.patch(
                f"/api/v1/tenants/{response.data['tenant']['id']}/",
                {'brand_color': '#123456'},
                format='json',
            ).status_code,
            200,
        )
        self.client.patch(
            f"/api/v1/tenants/{response.data['tenant']['id']}/",
            {'platform_commission_pct': '0.00', 'status': 'SUSPENDED'},
            format='json',
        )
        tenant = Tenant.objects.get(pk=response.data['tenant']['id'])
        self.assertEqual(str(tenant.platform_commission_pct), '10.00')
        self.assertEqual(tenant.status, Tenant.Status.ACTIVE)
        self.assertEqual(
            self.client.post('/api/v1/tenants/', {}, format='json').status_code,
            403,
        )

        created_customer = self.client.post(
            '/api/v1/customers/',
            {
                'tenant_id': response.data['tenant']['id'],
                'username': 'ada-subscriber',
                'name': 'Ada Subscriber',
                'phone_number': '+254700000001',
                'service_type': 'hotspot',
                'portal_password': 'Subscriber-Portal-Password-927!',
            },
            format='json',
        )
        self.assertEqual(created_customer.status_code, 201, created_customer.data)
        customer_user = get_user_model().objects.get(username='ada-subscriber')
        self.assertEqual(str(customer_user.customer_profile.pk), created_customer.data['id'])

        customer_login = self.client.post(
            '/api/v1/auth/login/',
            {'username': 'ada-subscriber', 'password': 'Subscriber-Portal-Password-927!'},
            format='json',
        )
        self.assertEqual(customer_login.status_code, 200, customer_login.data)
        self.assertEqual(customer_login.data['role'], 'CUSTOMER')

    def test_login_returns_tokens_and_vendor_metadata(self):
        registration = self.client.post(
            '/api/v1/auth/register/vendor/',
            {
                'email': 'login@example.com',
                'password': 'StrongPassword123!',
                'business_name': 'Login Hotspots',
                'phone_number': '+254711111111',
            },
            format='json',
        )
        self.assertEqual(registration.status_code, 201)

        response = self.client.post(
            '/api/v1/auth/login/',
            {'username': 'login@example.com', 'password': 'StrongPassword123!'},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)
        self.assertEqual(response.data['email'], 'login@example.com')
        self.assertEqual(response.data['role'], 'VENDOR')
        self.assertTrue(response.data['is_vendor'])


class RoleProvisioningAndPermissionTests(APITestCase):
    def test_superuser_creation_provisions_platform_profile_and_global_access(self):
        User = get_user_model()
        user = User.objects.create_superuser(
            username='root',
            email='root@example.com',
            password='StrongPassword123!',
        )

        self.assertEqual(user.platform_profile.role, PlatformUser.Role.SUPERADMIN)
        self.assertTrue(user.is_superadmin)

        login = self.client.post(
            '/api/v1/auth/login/',
            {'username': 'root', 'password': 'StrongPassword123!'},
            format='json',
        )
        self.assertEqual(login.status_code, 200)
        self.assertEqual(login.data['role'], 'SUPERADMIN')
        self.assertTrue(login.data['is_superadmin'])

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
        self.assertEqual(self.client.get('/api/v1/tenants/').status_code, 200)
        self.assertEqual(self.client.get('/api/v1/superadmin/metrics/').status_code, 200)
        created_admin = self.client.post(
            '/api/v1/superadmin/users/',
            {
                'username': 'platform-created-admin',
                'email': 'platform-created-admin@example.com',
                'role': PlatformUser.Role.SUPERADMIN,
                'password': 'Platform-Admin-Password-374!',
            },
            format='json',
        )
        self.assertEqual(created_admin.status_code, 201, created_admin.data)
        created_user = User.objects.get(username='platform-created-admin')
        self.assertTrue(created_user.is_superuser)
        self.assertEqual(PlatformUser.objects.filter(user=created_user).count(), 1)
        self.assertEqual(
            self.client.patch(
                f"/api/v1/superadmin/users/{created_admin.data['id']}/",
                {'role': PlatformUser.Role.SUPPORT_AGENT},
                format='json',
            ).status_code,
            200,
        )
        created_user.refresh_from_db()
        self.assertFalse(created_user.is_superuser)
        self.assertEqual(created_user.platform_profile.role, PlatformUser.Role.SUPPORT_AGENT)

    def test_platform_admin_profile_authorizes_global_access_without_tenant_profile(self):
        User = get_user_model()
        user = User.objects.create_user(
            username='platform-admin',
            email='platform-admin@example.com',
            password='StrongPassword123!',
        )
        PlatformUser.objects.create(user=user, role=PlatformUser.Role.SUPERADMIN)
        self.client.force_authenticate(user=user)

        self.assertTrue(user.is_superadmin)
        self.assertEqual(self.client.get('/api/v1/tenants/').status_code, 200)

        support_user = User.objects.create_user(
            username='support-agent',
            email='support-agent@example.com',
            password='StrongPassword123!',
        )
        PlatformUser.objects.create(user=support_user, role=PlatformUser.Role.SUPPORT_AGENT)
        self.client.force_authenticate(user=support_user)
        self.assertEqual(self.client.get('/api/v1/tenants/').status_code, 403)

    def test_inactive_superuser_is_denied_global_access(self):
        user = get_user_model().objects.create_superuser(
            username='inactive-root',
            email='inactive-root@example.com',
            password='StrongPassword123!',
        )
        user.is_active = False
        user.save(update_fields=['is_active'])
        self.client.force_authenticate(user=user)

        self.assertEqual(self.client.get('/api/v1/tenants/').status_code, 403)

    def test_customer_profile_claims_and_tenant_scope_do_not_grant_admin_access(self):
        User = get_user_model()
        tenant = Tenant.objects.create(
            business_name='Customer ISP',
            email='isp@example.com',
            phone_number='+254700000000',
        )
        customer_user = User.objects.create_user(
            username='subscriber',
            email='subscriber@example.com',
            password='StrongPassword123!',
        )
        Customer.objects.create(
            user=customer_user,
            tenant=tenant,
            username='subscriber',
            name='Subscriber',
            phone_number='+254711111111',
        )

        login = self.client.post(
            '/api/v1/auth/login/',
            {'username': 'subscriber', 'password': 'StrongPassword123!'},
            format='json',
        )
        self.assertEqual(login.status_code, 200)
        self.assertEqual(login.data['role'], 'CUSTOMER')
        self.assertEqual(login.data['tenant_id'], str(tenant.pk))
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")

        tenants = self.client.get('/api/v1/tenants/')
        self.assertEqual(tenants.status_code, 200)
        self.assertEqual([item['id'] for item in tenants.data], [str(tenant.pk)])
        self.assertEqual(self.client.get('/api/v1/superadmin/metrics/').status_code, 403)
        invoice = Invoice.objects.create(
            tenant=tenant,
            invoice_number='INV-CUSTOMER-001',
            customer_name='Subscriber',
            customer_phone='+254711111111',
            plan_name='Monthly',
            amount='100.00',
            date='2026-10-23',
            due_date='2026-10-23',
        )
        self.assertEqual(
            self.client.patch(
                f'/api/v1/invoices/{invoice.pk}/',
                {'status': 'PAID'},
                format='json',
            ).status_code,
            403,
        )

    def test_superuser_demotion_removes_superadmin_platform_role(self):
        user = get_user_model().objects.create_superuser(
            username='demoted-root',
            email='demoted-root@example.com',
            password='StrongPassword123!',
        )
        user.is_superuser = False
        user.is_staff = False
        user.save(update_fields=['is_superuser', 'is_staff'])

        self.assertEqual(user.platform_profile.role, PlatformUser.Role.SUPPORT_AGENT)
        self.assertFalse(user.is_superadmin)
