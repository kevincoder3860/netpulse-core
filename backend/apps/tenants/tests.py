from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase


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
