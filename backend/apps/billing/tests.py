import base64
import hashlib
import hmac
import io
import json
import uuid
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from urllib.error import HTTPError, URLError
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import OperationalError, connections
from django.db.models.query import QuerySet
from django.test import SimpleTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.billing.models import HotspotPlan, MpesaGatewayConfiguration, Transaction
from apps.radius.models import RadCheck, RadReply
from apps.billing.mpesa import (
    MpesaGatewayError, _api_root, _request_json, _timestamp_and_password, initiate_stk_push,
)
from apps.billing.paystack import (
    PaystackGatewayError,
    initiate_mobile_money_charge,
    normalize_kenyan_phone_number,
    _request_json as paystack_request_json,
    verify_webhook_signature,
)
from apps.billing.serializers import HotspotPlanSerializer
from apps.billing.services import (
    _sync_paid_user_to_router,
    get_routeros_timeout,
    sync_hotspot_plan_profile_to_routers,
)
from apps.billing.services import process_successful_payment
from apps.operations.models import Customer
from apps.routers.models import NAS
from apps.tenants.models import Tenant, TenantUser
from apps.vouchers.models import Recharge


class PublicPaymentEndpointTests(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            business_name='Payment Test ISP',
            email='payments@example.com',
            phone_number='+254700000000',
        )
        self.router = NAS.objects.create(
            tenant=self.tenant,
            nasname='payment-test-router',
            shortname='Payment Test',
            secret='test-radius-secret',
        )
        self.plan = HotspotPlan.objects.create(
            tenant=self.tenant,
            name='Test Plan',
            price='100.00',
            duration_minutes=60,
        )
        self.transaction = Transaction.objects.create(
            tenant=self.tenant,
            nas=self.router,
            plan=self.plan,
            gross_amount='100.00',
            platform_fee='10.00',
            vendor_net_amount='90.00',
            phone_number='+254711111111',
            client_mac='AA:BB:CC:DD:EE:FF',
            merchant_request_id=str(uuid.uuid4()),
            checkout_request_id=str(uuid.uuid4()),
        )

    def test_public_status_endpoint_does_not_expose_transaction_pii(self):
        response = self.client.get(
            f'/api/v1/transactions/{self.transaction.checkout_request_id}/status/'
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            set(response.data),
            {'checkout_request_id', 'status', 'updated_at'},
        )

    def test_unverified_mpesa_callback_is_not_processed(self):
        response = self.client.post(
            '/api/v1/mpesa/callback/',
            {
                'Body': {
                    'stkCallback': {
                        'CheckoutRequestID': self.transaction.checkout_request_id,
                        'ResultCode': 0,
                        'CallbackMetadata': {
                            'Item': [{'Name': 'MpesaReceiptNumber', 'Value': 'FAKE-RECEIPT'}],
                        },
                    },
                },
            },
            format='json',
        )

        self.assertEqual(response.status_code, 503)
        self.transaction.refresh_from_db()
        self.assertEqual(self.transaction.status, 'PENDING')
        self.assertIsNone(self.transaction.mpesa_receipt_number)

    def test_hotspot_profile_sync_uses_librouteros_query_key(self):
        self.router.is_online = True
        self.router.save(update_fields=['is_online'])
        connection = MagicMock()
        profile_path = connection.path.return_value
        profile_path.select.return_value.where.return_value = iter([{'.id': '*1'}])

        with patch('librouteros.connect', return_value=connection):
            sync_hotspot_plan_profile_to_routers(self.plan)

        where_call = profile_path.select.return_value.where.call_args
        self.assertIsNotNone(where_call)
        self.assertEqual(len(where_call.args), 1)
        self.assertEqual(list(where_call.args[0]), ['?=name=Test Plan'])
        profile_path.set.assert_called_once()
        self.assertEqual(profile_path.set.call_args.kwargs['session-timeout'], '60m')
        connection.close.assert_called_once()

    def test_hotspot_profile_sync_creates_profile_with_dynamic_session_timeout(self):
        self.router.is_online = True
        self.router.save(update_fields=['is_online'])
        self.plan.duration_value = 2
        self.plan.duration_unit = 'days'
        self.plan.duration_minutes = 2880
        self.plan.save(update_fields=['duration_value', 'duration_unit', 'duration_minutes'])

        connection = MagicMock()
        profile_path = connection.path.return_value
        profile_path.select.return_value.where.return_value = iter([])

        with patch('librouteros.connect', return_value=connection):
            sync_hotspot_plan_profile_to_routers(self.plan)

        self.assertEqual(profile_path.add.call_args.kwargs['session-timeout'], '2d')

    def test_plan_serializer_accepts_dynamic_duration_and_preserves_legacy_minutes(self):
        dynamic = HotspotPlanSerializer(data={
            'tenant': str(self.tenant.id),
            'name': 'Two Hour Plan',
            'price': '150.00',
            'duration_value': 2,
            'duration_unit': 'hours',
        })
        self.assertTrue(dynamic.is_valid(), dynamic.errors)
        dynamic_plan = dynamic.save()
        self.assertEqual(dynamic_plan.duration_value, 2)
        self.assertEqual(dynamic_plan.duration_unit, 'hours')
        self.assertEqual(dynamic_plan.duration_minutes, 120)

        legacy = HotspotPlanSerializer(data={
            'tenant': str(self.tenant.id),
            'name': 'Legacy 90 Minute Plan',
            'price': '90.00',
            'duration_minutes': 90,
        })
        self.assertTrue(legacy.is_valid(), legacy.errors)
        legacy_plan = legacy.save()
        self.assertEqual(legacy_plan.duration_value, 90)
        self.assertEqual(legacy_plan.duration_unit, 'minutes')

    def test_routeros_timeout_formatting(self):
        self.assertEqual(get_routeros_timeout(30, 'minutes'), '30m')
        self.assertEqual(get_routeros_timeout(1, 'hour'), '1h')
        self.assertEqual(get_routeros_timeout(2, 'days'), '2d')
        self.assertEqual(get_routeros_timeout(4, 'unknown'), '4h')


class MpesaGatewayConfigurationApiTests(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            business_name='Daraja Vendor',
            email='daraja-vendor@example.com',
            phone_number='+254700000002',
        )
        self.user = get_user_model().objects.create_user(
            username='daraja-vendor',
            email='daraja-vendor@example.com',
            password='StrongPassword123!',
        )
        TenantUser.objects.create(user=self.user, tenant=self.tenant, role=TenantUser.Role.VENDOR)
        self.client.force_authenticate(user=self.user)

    def test_gateway_settings_start_unconfigured_without_exposing_secrets(self):
        response = self.client.get('/api/v1/billing/mpesa/configuration/')

        self.assertEqual(response.status_code, 200, response.data)
        self.assertFalse(response.data['configured'])
        self.assertFalse(response.data['consumer_key_set'])
        self.assertNotIn('consumer_key', response.data)

    def test_empty_configuration_put_is_a_safe_noop(self):
        response = self.client.put(
            '/api/v1/billing/mpesa/configuration/',
            {},
            format='json',
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertFalse(response.data['configured'])
        self.assertFalse(MpesaGatewayConfiguration.objects.filter(tenant=self.tenant).exists())

    def test_partial_configuration_put_creates_an_incomplete_configuration(self):
        response = self.client.put(
            '/api/v1/billing/mpesa/configuration/',
            {'environment': 'sandbox', 'shortcode': '123456'},
            format='json',
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertFalse(response.data['configured'])
        configuration = MpesaGatewayConfiguration.objects.get(tenant=self.tenant)
        self.assertEqual(configuration.shortcode, '123456')
        self.assertFalse(configuration.consumer_key_encrypted)

    def test_gateway_credentials_are_encrypted_and_never_returned(self):
        response = self.client.put(
            '/api/v1/billing/mpesa/configuration/',
            {
                'environment': 'sandbox',
                'merchant_type': 'CustomerPayBillOnline',
                'shortcode': '123456',
                'consumer_key': 'consumer-key-value',
                'consumer_secret': 'consumer-secret-value',
                'passkey': 'lipa-passkey-value',
            },
            format='json',
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data['configured'])
        self.assertNotIn('consumer-secret-value', str(response.data))
        configuration = MpesaGatewayConfiguration.objects.get(tenant=self.tenant)
        self.assertNotIn('consumer-key-value', configuration.consumer_key_encrypted)
        self.assertNotIn('consumer-secret-value', configuration.consumer_secret_encrypted)
        self.assertNotIn('lipa-passkey-value', configuration.passkey_encrypted)
        self.assertEqual(configuration.get_credentials(), {
            'consumer_key': 'consumer-key-value',
            'consumer_secret': 'consumer-secret-value',
            'passkey': 'lipa-passkey-value',
        })

        get_response = self.client.get('/api/v1/billing/mpesa/configuration/')
        self.assertEqual(get_response.status_code, 200)
        self.assertTrue(get_response.data['consumer_secret_set'])
        self.assertNotIn('consumer_secret', get_response.data)

    def test_configuration_updates_are_scoped_to_the_authenticated_vendor(self):
        other_tenant = Tenant.objects.create(
            business_name='Other ISP',
            email='other-daraja@example.com',
            phone_number='+254700000003',
        )
        other_configuration = MpesaGatewayConfiguration.objects.create(
            tenant=other_tenant,
            shortcode='654321',
            consumer_key_encrypted='other-key',
            consumer_secret_encrypted='other-secret',
            passkey_encrypted='other-passkey',
        )

        response = self.client.put(
            '/api/v1/billing/mpesa/configuration/',
            {'shortcode': '123456'},
            format='json',
        )

        self.assertEqual(response.status_code, 200, response.data)
        other_configuration.refresh_from_db()
        self.assertEqual(other_configuration.shortcode, '654321')
        self.assertEqual(MpesaGatewayConfiguration.objects.filter(tenant=self.tenant).count(), 1)


class MpesaStkPushApiTests(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            business_name='STK Test ISP',
            email='stk-test@example.com',
            phone_number='+254700000004',
        )
        self.router = NAS.objects.create(
            tenant=self.tenant,
            nasname='stk-test-router',
            shortname='STK Test',
            secret='test-radius-secret',
        )
        self.plan = HotspotPlan.objects.create(
            tenant=self.tenant,
            name='Hourly Wi-Fi',
            price='100.00',
            duration_minutes=60,
        )
        self.configuration = MpesaGatewayConfiguration.objects.create(
            tenant=self.tenant,
            shortcode='123456',
            consumer_key_encrypted=MpesaGatewayConfiguration.encrypt_credential('test-key'),
            consumer_secret_encrypted=MpesaGatewayConfiguration.encrypt_credential('test-secret'),
            passkey_encrypted=MpesaGatewayConfiguration.encrypt_credential('test-passkey'),
        )

    @patch('apps.billing.views.initiate_stk_push')
    def test_stk_push_uses_server_plan_amount_and_persists_checkout(self, initiate):
        initiate.return_value = {
            'message': 'STK push sent',
            'checkout_request_id': 'ws_CO_test_checkout',
            'merchant_request_id': 'test-merchant-request',
        }
        response = self.client.post(
            '/api/v1/billing/mpesa/stk-push/',
            {
                'nas_id': str(self.router.id),
                'plan_id': self.plan.id,
                'phone_number': '254712345678',
                'amount': '100.00',
                'mac_address': '02:00:00:00:00:02',
            },
            format='json',
        )

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['amount'], 100)
        self.assertEqual(response.data['checkout_request_id'], 'ws_CO_test_checkout')
        initiate.assert_called_once()
        self.assertEqual(initiate.call_args.kwargs['amount'], 100)
        payment = Transaction.objects.get(checkout_request_id='ws_CO_test_checkout')
        self.assertEqual(payment.tenant, self.tenant)
        self.assertEqual(payment.plan, self.plan)
        self.assertEqual(str(payment.gross_amount), '100.00')

    @patch('apps.billing.views.initiate_stk_push')
    def test_stk_push_rejects_amount_mismatch_before_contacting_provider(self, initiate):
        response = self.client.post(
            '/api/v1/billing/mpesa/stk-push/',
            {
                'nas_id': str(self.router.id),
                'plan_id': self.plan.id,
                'phone_number': '254712345678',
                'amount': '1.00',
                'mac_address': '02:00:00:00:00:02',
            },
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        initiate.assert_not_called()

    @patch('apps.billing.views.initiate_stk_push')
    def test_daraja_validation_error_returns_structured_bad_request(self, initiate):
        initiate.side_effect = MpesaGatewayError(
            'Bad Request - Invalid TransactionType',
            code='DARAJA_HTTP_ERROR',
            gateway_status=400,
            provider_error_code='400.002.02',
        )
        response = self.client.post(
            '/api/v1/billing/mpesa/stk-push/',
            {
                'nas_id': str(self.router.id),
                'plan_id': self.plan.id,
                'phone_number': '254712345678',
                'amount': '100.00',
                'mac_address': '02:00:00:00:00:02',
            },
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data, {
            'detail': 'Bad Request - Invalid TransactionType',
            'code': 'DARAJA_HTTP_ERROR',
            'gateway_status': 400,
            'provider_error_code': '400.002.02',
        })

    @patch('apps.billing.services.process_successful_payment')
    @patch('apps.billing.views.query_stk_status')
    def test_status_is_completed_only_after_daraja_confirms_success(self, query_status, process_payment):
        payment = Transaction.objects.create(
            tenant=self.tenant,
            nas=self.router,
            plan=self.plan,
            gross_amount=self.plan.price,
            platform_fee='10.00',
            vendor_net_amount='90.00',
            phone_number='254712345678',
            merchant_request_id='test-merchant-request',
            checkout_request_id='ws_CO_pending',
            client_mac='02:00:00:00:00:02',
        )
        query_status.return_value = {'ResponseCode': '0', 'ResultCode': '0'}

        def complete_payment(_payment_id):
            Transaction.objects.filter(pk=payment.pk).update(status='COMPLETED')
            payment.refresh_from_db()
            return payment

        process_payment.side_effect = complete_payment
        response = self.client.get('/api/v1/transactions/ws_CO_pending/status/')

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['status'], 'COMPLETED')
        query_status.assert_called_once_with(self.configuration, 'ws_CO_pending')
        process_payment.assert_called_once_with(str(payment.id))


class MpesaDarajaServiceTests(APITestCase):
    def setUp(self):
        tenant = Tenant.objects.create(
            business_name='Daraja Service Test',
            email='daraja-service@example.com',
            phone_number='+254700000005',
        )
        self.configuration = MpesaGatewayConfiguration.objects.create(
            tenant=tenant,
            shortcode='123456',
            environment='sandbox',
            consumer_key_encrypted=MpesaGatewayConfiguration.encrypt_credential('consumer-key'),
            consumer_secret_encrypted=MpesaGatewayConfiguration.encrypt_credential('consumer-secret'),
            passkey_encrypted=MpesaGatewayConfiguration.encrypt_credential('test-passkey'),
        )

    @patch('apps.billing.mpesa._request_json')
    def test_initiate_stk_push_authenticates_and_sends_gateway_payload(self, request_json):
        cache.clear()
        request_json.side_effect = [
            {'access_token': 'test-access-token', 'expires_in': '3600'},
            {
                'ResponseCode': '0',
                'CheckoutRequestID': 'ws_CO_service_test',
                'MerchantRequestID': 'merchant_service_test',
                'CustomerMessage': 'Check your phone',
            },
        ]

        response = initiate_stk_push(
            self.configuration,
            phone_number='254712345678',
            amount=120,
            reference='One Hour Plan',
            callback_url='https://example.test/api/v1/mpesa/callback/',
        )

        self.assertEqual(response['checkout_request_id'], 'ws_CO_service_test')
        self.assertEqual(request_json.call_args_list[0].args[0], (
            'https://sandbox.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials'
        ))
        expected_credentials = base64.b64encode(
            b'consumer-key:consumer-secret'
        ).decode()
        self.assertEqual(
            request_json.call_args_list[0].kwargs['headers']['Authorization'],
            f'Basic {expected_credentials}',
        )
        push_call = request_json.call_args_list[1]
        self.assertEqual(
            push_call.args[0],
            'https://sandbox.safaricom.co.ke/mpesa/stkpush/v1/processrequest',
        )
        self.assertEqual(push_call.kwargs['headers']['Authorization'], 'Bearer test-access-token')
        self.assertEqual(push_call.kwargs['payload']['Amount'], 120)
        self.assertIsInstance(push_call.kwargs['payload']['Amount'], int)
        self.assertEqual(push_call.kwargs['payload']['BusinessShortCode'], '123456')
        self.assertEqual(push_call.kwargs['payload']['PartyA'], '254712345678')
        self.assertEqual(push_call.kwargs['payload']['PartyB'], '123456')
        self.assertEqual(push_call.kwargs['payload']['AccountReference'], 'One Hour Plan')
        self.assertEqual(push_call.kwargs['payload']['TransactionDesc'], 'Hotspot Plan Purchase')
        self.assertEqual(
            push_call.kwargs['payload']['TransactionType'],
            'CustomerPayBillOnline',
        )
        self.assertEqual(
            base64.b64decode(push_call.kwargs['payload']['Password']),
            f"123456test-passkey{push_call.kwargs['payload']['Timestamp']}".encode(),
        )
        self.assertEqual(push_call.kwargs['payload']['PhoneNumber'], '254712345678')
        self.assertEqual(
            push_call.kwargs['payload']['CallBackURL'],
            'https://example.test/api/v1/mpesa/callback/',
        )

    @patch('apps.billing.mpesa._request_json')
    def test_stk_push_uses_configured_buy_goods_transaction_type(self, request_json):
        cache.clear()
        self.configuration.merchant_type = MpesaGatewayConfiguration.MerchantType.BUY_GOODS
        request_json.side_effect = [
            {'access_token': 'test-access-token', 'expires_in': '3600'},
            {
                'ResponseCode': '0',
                'CheckoutRequestID': 'ws_CO_buy_goods_test',
                'MerchantRequestID': 'merchant_buy_goods_test',
            },
        ]

        initiate_stk_push(
            self.configuration,
            phone_number='254712345678',
            amount=120,
            reference='One Hour Plan Plus',
            callback_url='https://example.test/api/v1/mpesa/callback/',
        )

        self.assertEqual(
            request_json.call_args_list[1].kwargs['payload']['TransactionType'],
            'CustomerBuyGoodsOnline',
        )
        self.assertEqual(
            request_json.call_args_list[1].kwargs['payload']['PartyB'],
            str(self.configuration.shortcode),
        )
        self.assertEqual(
            request_json.call_args_list[1].kwargs['payload']['AccountReference'],
            'One Hour Plan Plus',
        )
        self.assertEqual(
            request_json.call_args_list[1].kwargs['payload']['TransactionDesc'],
            'Hotspot Plan Purchase',
        )

    @patch('apps.billing.mpesa._request_json')
    def test_stk_push_rejects_an_unsupported_merchant_type(self, request_json):
        self.configuration.merchant_type = 'UNKNOWN'

        with self.assertRaisesRegex(MpesaGatewayError, 'merchant type'):
            initiate_stk_push(
                self.configuration,
                phone_number='254712345678',
                amount=120,
                reference='One Hour Plan',
                callback_url='https://example.test/api/v1/mpesa/callback/',
            )
        request_json.assert_not_called()

    @patch('apps.billing.mpesa._request_json')
    def test_oauth_failure_is_logged_and_prevents_stk_push(self, request_json):
        cache.clear()
        request_json.return_value = {
            'error': 'invalid_client',
            'error_description': 'Invalid client credentials',
        }

        with self.assertLogs('apps.billing.mpesa', level='WARNING') as captured:
            with self.assertRaises(MpesaGatewayError):
                initiate_stk_push(
                    self.configuration,
                    phone_number='254712345678',
                    amount=120,
                    reference='One Hour Plan',
                    callback_url='https://example.test/api/v1/mpesa/callback/',
                )

        self.assertIn('invalid_client', captured.output[0])
        self.assertIn('Invalid client credentials', captured.output[0])
        request_json.assert_called_once()

    def test_stk_password_combines_shortcode_passkey_and_formatted_timestamp(self):
        timestamp, password = _timestamp_and_password(self.configuration)

        self.assertRegex(timestamp, r'^\d{14}$')
        self.assertEqual(
            base64.b64decode(password),
            f'123456test-passkey{timestamp}'.encode(),
        )


class MpesaRequestLoggingTests(SimpleTestCase):
    def test_api_root_uses_sandbox_and_production_configuration(self):
        self.assertEqual(
            _api_root(SimpleNamespace(environment='sandbox')),
            'https://sandbox.safaricom.co.ke',
        )
        self.assertEqual(
            _api_root(SimpleNamespace(environment=' PRODUCTION ')),
            'https://api.safaricom.co.ke',
        )
        with self.assertRaises(MpesaGatewayError):
            _api_root(SimpleNamespace(environment='unknown'))

    @patch('apps.billing.mpesa.urlopen')
    def test_http_error_logs_status_url_and_provider_error_text(self, urlopen):
        url = 'https://sandbox.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials'
        error_body = '{"errorCode":"400.002.02","errorMessage":"Bad Request - Invalid TransactionType"}'
        urlopen.side_effect = HTTPError(
            url,
            400,
            'Bad Request',
            hdrs=None,
            fp=io.BytesIO(error_body.encode()),
        )

        with self.assertLogs('apps.billing.mpesa', level='ERROR') as captured:
            with self.assertRaises(MpesaGatewayError) as raised:
                _request_json(url)

        log_output = '\n'.join(captured.output)
        self.assertIn('status=400', log_output)
        self.assertIn(url, log_output)
        self.assertIn('Bad Request - Invalid TransactionType', log_output)
        self.assertIn(error_body, log_output)
        self.assertNotIn('Traceback', log_output)
        self.assertEqual(str(raised.exception), 'Bad Request - Invalid TransactionType')
        self.assertEqual(raised.exception.gateway_status, 400)
        self.assertEqual(raised.exception.provider_error_code, '400.002.02')
        self.assertEqual(raised.exception.code, 'DARAJA_HTTP_ERROR')

    @patch('apps.billing.mpesa.urlopen')
    def test_connection_error_logs_url_and_transport_error(self, urlopen):
        url = 'https://api.safaricom.co.ke/mpesa/stkpush/v1/processrequest'
        urlopen.side_effect = URLError('connection refused')

        with self.assertLogs('apps.billing.mpesa', level='ERROR') as captured:
            with self.assertRaises(MpesaGatewayError):
                _request_json(url, method='POST')

        self.assertIn('status=unavailable', captured.output[0])
        self.assertIn(url, captured.output[0])
        self.assertIn('connection refused', captured.output[0])


class PaystackGatewaySettingsApiTests(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            business_name='Paystack Vendor',
            email='vendor@example.com',
            phone_number='+254700000010',
        )
        self.user = get_user_model().objects.create_user(
            username='paystack-vendor',
            email='vendor@example.com',
            password='StrongPassword123!',
        )
        TenantUser.objects.create(
            user=self.user,
            tenant=self.tenant,
            role=TenantUser.Role.VENDOR,
        )
        self.client.force_authenticate(user=self.user)

    def test_vendor_can_patch_billing_email_and_secret_without_returning_secret(self):
        secret = 'sk_test_per_vendor_secret'
        response = self.client.patch(
            f'/api/v1/tenants/{self.tenant.id}/',
            {
                'billing_email': 'receipts@example.com',
                'paystack_secret_key': secret,
            },
            format='json',
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['billing_email'], 'receipts@example.com')
        self.assertTrue(response.data['paystack_secret_key_set'])
        self.assertNotIn('paystack_secret_key', response.data)
        self.tenant.refresh_from_db()
        self.assertNotEqual(self.tenant.paystack_secret_key, secret)
        self.assertEqual(self.tenant.get_paystack_secret_key(), secret)

    def test_blank_secret_patch_preserves_saved_key(self):
        secret = 'sk_test_keep_existing'
        self.tenant.set_paystack_secret_key(secret)
        self.tenant.save(update_fields=['paystack_secret_key', 'updated_at'])

        response = self.client.patch(
            f'/api/v1/tenants/{self.tenant.id}/',
            {'paystack_secret_key': ''},
            format='json',
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.get_paystack_secret_key(), secret)


class PaystackMobileMoneyServiceTests(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            business_name='Paystack Service ISP',
            email='service@example.com',
            billing_email='settlements@example.com',
            phone_number='+254700000011',
        )
        self.tenant.set_paystack_secret_key('sk_test_service_secret')
        self.tenant.save(update_fields=['paystack_secret_key', 'updated_at'])

    @patch('apps.billing.paystack.urlopen')
    def test_paystack_requests_use_custom_user_agent(self, urlopen_mock):
        response = MagicMock()
        response.status = 200
        response.read.return_value = b'{"status":true}'
        urlopen_mock.return_value.__enter__.return_value = response

        result = paystack_request_json(
            'https://api.paystack.co/transaction/verify/ref-123',
            secret_key='sk_test_service_secret',
        )

        self.assertEqual(result, {'status': True})
        request = urlopen_mock.call_args.args[0]
        self.assertEqual(request.get_header('User-agent'), 'NeonISP-Billing/1.0')
        self.assertEqual(request.get_header('Authorization'), 'Bearer sk_test_service_secret')

    @override_settings(PAYSTACK_SECRET_KEY='sk_test_environment_fallback')
    @patch('apps.billing.paystack._request_json')
    def test_charge_sends_kes_cents_and_normalized_phone(self, request_json):
        request_json.return_value = {
            'status': True,
            'message': 'Charge attempted',
            'data': {'reference': 'paystack-ref-123', 'display_text': 'Check your phone'},
        }

        result = initiate_mobile_money_charge(
            self.tenant,
            phone_number='0712345678',
            amount='12.50',
        )

        self.assertEqual(result['reference'], 'paystack-ref-123')
        self.assertEqual(result['phone_number'], '+254712345678')
        self.assertEqual(result['amount_cents'], 1250)
        self.assertEqual(request_json.call_args.args[0], 'https://api.paystack.co/charge')
        self.assertEqual(request_json.call_args.kwargs['method'], 'POST')
        self.assertEqual(
            request_json.call_args.kwargs['payload'],
            {
                'email': 'settlements@example.com',
                'amount': 1250,
                'currency': 'KES',
                'mobile_money': {
                    'phone': '+254712345678',
                    'provider': 'mpesa',
                },
            },
        )
        self.assertEqual(
            request_json.call_args.kwargs['secret_key'],
            'sk_test_service_secret',
        )

    @override_settings(PAYSTACK_SECRET_KEY='sk_test_environment_fallback')
    @patch('apps.billing.paystack._request_json')
    def test_environment_key_is_used_only_when_tenant_key_is_empty(self, request_json):
        self.tenant.paystack_secret_key = ''
        self.tenant.save(update_fields=['paystack_secret_key', 'updated_at'])
        request_json.return_value = {
            'status': True,
            'data': {'reference': 'fallback-ref'},
        }

        initiate_mobile_money_charge(
            self.tenant,
            phone_number='0712345678',
            amount='12.50',
        )

        self.assertEqual(
            request_json.call_args.kwargs['secret_key'],
            'sk_test_environment_fallback',
        )

    @patch('apps.billing.paystack.urlopen')
    def test_http_forbidden_logs_and_preserves_paystack_error_message(self, urlopen_mock):
        urlopen_mock.side_effect = HTTPError(
            'https://api.paystack.co/charge',
            403,
            'Forbidden',
            {},
            io.BytesIO(b'{"status":false,"message":"Invalid key"}'),
        )

        with self.assertLogs('apps.billing.paystack', level='WARNING') as logs:
            with self.assertRaises(PaystackGatewayError) as raised:
                initiate_mobile_money_charge(
                    self.tenant,
                    phone_number='0712345678',
                    amount='12.50',
                )

        self.assertEqual(raised.exception.gateway_status, 403)
        self.assertEqual(str(raised.exception), 'Invalid key')
        self.assertIn('Paystack request failed with HTTP 403: Invalid key', logs.output[0])

    def test_phone_normalization_accepts_local_and_international_formats(self):
        for value in ('0712345678', '0112345678', '254712345678', '+254112345678'):
            with self.subTest(value=value):
                self.assertEqual(
                    normalize_kenyan_phone_number(value),
                    f'+{value.lstrip("+").lstrip("0")}' if value.startswith('254') or value.startswith('+254')
                    else f'+254{value[1:]}',
                )

    def test_phone_normalization_rejects_non_kenyan_numbers(self):
        with self.assertRaises(PaystackGatewayError):
            normalize_kenyan_phone_number('071234567')

    def test_webhook_signature_uses_tenant_secret(self):
        body = b'{"event":"charge.success"}'
        signature = hmac.new(
            b'sk_test_service_secret',
            body,
            hashlib.sha512,
        ).hexdigest()

        self.assertTrue(verify_webhook_signature(self.tenant, body, signature))
        self.assertFalse(verify_webhook_signature(self.tenant, body, 'invalid'))


class PaystackStkPushApiTests(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            business_name='Paystack STK ISP',
            email='stk@example.com',
            billing_email='receipts@example.com',
            phone_number='+254700000012',
        )
        self.tenant.set_paystack_secret_key('sk_test_stk_secret')
        self.tenant.save(update_fields=['paystack_secret_key', 'updated_at'])
        self.router = NAS.objects.create(
            tenant=self.tenant,
            nasname='paystack-router',
            shortname='Paystack',
            secret='radius-secret',
        )
        self.plan = HotspotPlan.objects.create(
            tenant=self.tenant,
            name='Hourly Wi-Fi',
            price='12.50',
            duration_minutes=60,
        )

    @patch('apps.billing.views.initiate_mobile_money_charge')
    def test_stk_push_uses_tenant_plan_and_persists_provider_reference(self, initiate):
        initiate.return_value = {
            'reference': 'paystack-charge-123',
            'phone_number': '+254712345678',
            'amount_cents': 1250,
            'message': 'Check your phone',
        }

        response = self.client.post(
            '/api/v1/billing/paystack/stk-push/',
            {
                'tenant_id': str(self.tenant.id),
                'plan_id': self.plan.id,
                'phone_number': '0712345678',
                'nas_id': self.router.id,
                'mac_address': '02:00:00:00:00:12',
            },
            format='json',
        )

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['reference'], 'paystack-charge-123')
        self.assertEqual(response.data['checkout_request_id'], 'paystack-charge-123')
        initiate.assert_called_once_with(
            self.tenant,
            phone_number='0712345678',
            amount=Decimal('12.50'),
        )
        payment = Transaction.objects.get(checkout_request_id='paystack-charge-123')
        self.assertEqual(payment.status, 'PENDING')
        self.assertEqual(payment.payment_method, 'PAYSTACK_MOBILE_MONEY')
        self.assertEqual(payment.phone_number, '+254712345678')
        self.assertEqual(payment.tenant_id, self.tenant.id)

    @patch('apps.billing.views.initiate_mobile_money_charge')
    def test_upstream_forbidden_is_returned_as_gateway_error_with_provider_message(self, initiate):
        initiate.side_effect = PaystackGatewayError(
            'Invalid key',
            code='PAYSTACK_HTTP_ERROR',
            gateway_status=403,
        )

        response = self.client.post(
            '/api/v1/billing/paystack/stk-push/',
            {
                'tenant_id': str(self.tenant.id),
                'plan_id': self.plan.id,
                'phone_number': '0712345678',
            },
            format='json',
        )

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.data['detail'], 'Invalid key')
        self.assertEqual(response.data['gateway_status'], 403)

    @patch('apps.billing.services.process_successful_payment')
    def test_charge_success_webhook_verifies_signature_and_activates_payment(self, process_payment):
        payment = Transaction.objects.create(
            tenant=self.tenant,
            nas=self.router,
            plan=self.plan,
            gross_amount=self.plan.price,
            platform_fee='1.25',
            vendor_net_amount='11.25',
            phone_number='+254712345678',
            merchant_request_id='paystack-webhook-ref',
            checkout_request_id='paystack-webhook-ref',
            client_mac='02:00:00:00:00:12',
            payment_method='PAYSTACK_MOBILE_MONEY',
        )
        payload = {
            'event': 'charge.success',
            'data': {
                'reference': payment.checkout_request_id,
                'status': 'success',
                'amount': 1250,
                'currency': 'KES',
            },
        }
        body = json.dumps(payload, separators=(',', ':')).encode()
        signature = hmac.new(
            b'sk_test_stk_secret',
            body,
            hashlib.sha512,
        ).hexdigest()
        process_payment.return_value = payment

        response = self.client.generic(
            'POST',
            '/api/v1/billing/paystack/webhook/',
            body,
            content_type='application/json',
            HTTP_X_PAYSTACK_SIGNATURE=signature,
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['status'], 'accepted')
        process_payment.assert_called_once_with(
            str(payment.id),
            provider_data=payload['data'],
        )

    @patch('apps.billing.services.process_successful_payment')
    def test_webhook_rejects_invalid_signature_and_wrong_amount(self, process_payment):
        payment = Transaction.objects.create(
            tenant=self.tenant,
            nas=self.router,
            plan=self.plan,
            gross_amount=self.plan.price,
            platform_fee='1.25',
            vendor_net_amount='11.25',
            phone_number='+254712345678',
            merchant_request_id='paystack-invalid-ref',
            checkout_request_id='paystack-invalid-ref',
            client_mac='02:00:00:00:00:12',
            payment_method='PAYSTACK_MOBILE_MONEY',
        )
        payload = {
            'event': 'charge.success',
            'data': {
                'reference': payment.checkout_request_id,
                'status': 'success',
                'amount': 1,
                'currency': 'KES',
            },
        }
        body = json.dumps(payload, separators=(',', ':')).encode()

        invalid_signature_response = self.client.generic(
            'POST',
            '/api/v1/billing/paystack/webhook/',
            body,
            content_type='application/json',
            HTTP_X_PAYSTACK_SIGNATURE='invalid',
        )
        self.assertEqual(invalid_signature_response.status_code, 401)

        signature = hmac.new(b'sk_test_stk_secret', body, hashlib.sha512).hexdigest()
        wrong_amount_response = self.client.generic(
            'POST',
            '/api/v1/billing/paystack/webhook/',
            body,
            content_type='application/json',
            HTTP_X_PAYSTACK_SIGNATURE=signature,
        )
        self.assertEqual(wrong_amount_response.status_code, 400)
        process_payment.assert_not_called()

    @patch('apps.billing.views.verify_mobile_money_charge')
    @patch('apps.billing.services.process_successful_payment')
    def test_pending_status_verifies_paystack_charge(self, process_payment, verify_charge):
        payment = Transaction.objects.create(
            tenant=self.tenant,
            nas=self.router,
            plan=self.plan,
            gross_amount=self.plan.price,
            platform_fee='1.25',
            vendor_net_amount='11.25',
            phone_number='+254712345678',
            merchant_request_id='paystack-status-ref',
            checkout_request_id='paystack-status-ref',
            client_mac='02:00:00:00:00:12',
            payment_method='PAYSTACK_MOBILE_MONEY',
        )
        verify_charge.return_value = {
            'reference': payment.checkout_request_id,
            'status': 'success',
            'amount': 1250,
            'currency': 'KES',
        }

        def complete_payment(_payment_id, *, provider_data=None):
            Transaction.objects.filter(pk=payment.pk).update(status='COMPLETED')
            payment.refresh_from_db()
            return payment

        process_payment.side_effect = complete_payment
        response = self.client.get(
            f'/api/v1/transactions/{payment.checkout_request_id}/status/'
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['status'], 'COMPLETED')
        verify_charge.assert_called_once_with(self.tenant, payment.checkout_request_id)
        process_payment.assert_called_once_with(
            str(payment.id),
            provider_data=verify_charge.return_value,
        )


class PaystackRadiusProvisioningTests(APITestCase):
    databases = {'default', 'radius_db'}

    def setUp(self):
        self.tenant = Tenant.objects.create(
            business_name='RADIUS Provisioning ISP',
            email='radius-provisioning@example.com',
            phone_number='+254700000013',
        )
        self.tenant.set_paystack_secret_key('sk_test_radius_provisioning')
        self.tenant.save(update_fields=['paystack_secret_key', 'updated_at'])
        self.plan = HotspotPlan.objects.create(
            tenant=self.tenant,
            name='RADIUS Access Plan',
            price='12.50',
            duration_minutes=45,
            download_speed_kbps=4096,
            upload_speed_kbps=1024,
        )
        self.payment = Transaction.objects.create(
            tenant=self.tenant,
            nas=None,
            plan=self.plan,
            gross_amount=self.plan.price,
            platform_fee='1.25',
            vendor_net_amount='11.25',
            phone_number='+254712345678',
            merchant_request_id='radius-provisioning-ref',
            checkout_request_id='radius-provisioning-ref',
            client_mac='02:00:00:00:00:13',
            payment_method='PAYSTACK_MOBILE_MONEY',
        )

    @patch('apps.billing.views.verify_mobile_money_charge')
    def test_paid_status_provisions_radius_credentials_and_replies(self, verify_charge):
        verify_charge.return_value = {
            'reference': self.payment.checkout_request_id,
            'status': 'success',
            'amount': 1250,
            'currency': 'KES',
            'receipt': 'MPS-TEST-RECEIPT',
            'fees': 100,
            'paid_at': timezone.now().isoformat(),
        }

        response = self.client.get(
            f'/api/v1/transactions/{self.payment.checkout_request_id}/status/'
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['status'], 'COMPLETED')
        self.assertEqual(response.data['hotspot_username'], self.payment.phone_number)
        self.assertEqual(response.data['hotspot_password'], self.payment.phone_number)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.gateway_receipt, 'MPS-TEST-RECEIPT')
        self.assertEqual(self.payment.gateway_fee, Decimal('1.00'))
        self.assertIsNotNone(self.payment.paid_at)

        customer = Customer.objects.get(tenant=self.tenant, username=self.payment.client_mac)
        recharge = Recharge.objects.get(transaction=self.payment)
        self.assertEqual(customer.tenant_id, self.tenant.id)
        self.assertEqual(customer.service_type, Customer.ServiceType.HOTSPOT)
        self.assertEqual(customer.status, Customer.Status.ACTIVE)
        self.assertEqual(customer.plan_name, self.plan.name)
        self.assertEqual(recharge.tenant_id, self.tenant.id)
        self.assertEqual(customer.expires_at, recharge.expires_at)
        self.assertEqual(recharge.method, 'SYSTEM')

        expiry = recharge.expires_at
        process_successful_payment(
            str(self.payment.id),
            provider_data=verify_charge.return_value,
        )
        self.assertEqual(Recharge.objects.filter(transaction=self.payment).count(), 1)
        recharge.refresh_from_db()
        customer.refresh_from_db()
        self.assertEqual(recharge.expires_at, expiry)
        self.assertEqual(customer.expires_at, expiry)

    @patch('apps.billing.services._sync_paid_user_to_router')
    def test_payment_uses_only_a_router_bound_to_its_tenant(self, sync_router):
        other_tenant = Tenant.objects.create(
            business_name='Other RADIUS ISP',
            email='other-radius@example.com',
            phone_number='+254700000014',
        )
        foreign_router = NAS.objects.create(
            tenant=other_tenant,
            nasname='foreign-payment-router',
            shortname='Foreign Router',
            secret='foreign-radius-secret',
            type='mikrotik',
        )
        tenant_router = NAS.objects.create(
            tenant=self.tenant,
            nasname='tenant-payment-router',
            shortname='Tenant Router',
            secret='tenant-radius-secret',
            type='mikrotik',
            is_online=False,
        )
        self.payment.nas = foreign_router
        self.payment.save(update_fields=['nas'])

        process_successful_payment(str(self.payment.id))

        self.payment.refresh_from_db()
        recharge = Recharge.objects.get(transaction=self.payment)
        self.assertEqual(self.payment.nas_id, tenant_router.id)
        self.assertEqual(recharge.router_id, tenant_router.id)
        sync_router.assert_called_once_with(
            tenant_router,
            self.plan,
            self.payment.phone_number,
            self.payment.client_mac,
        )

    @patch('apps.billing.services._sync_paid_user_to_router')
    def test_voucher_uses_device_mac_when_no_phone_number_is_present(self, sync_router):
        self.payment.phone_number = ''
        self.payment.payment_method = 'VOUCHER'
        self.payment.save(update_fields=['phone_number', 'payment_method', 'updated_at'])

        process_successful_payment(str(self.payment.id))

        sync_router.assert_called_once_with(
            None,
            self.plan,
            self.payment.client_mac,
            self.payment.client_mac,
        )

    @patch('apps.billing.services._sync_paid_user_to_router')
    def test_paid_payment_does_not_fall_back_to_mac_without_phone_number(self, sync_router):
        self.payment.phone_number = ''
        self.payment.save(update_fields=['phone_number', 'updated_at'])

        with self.assertRaisesMessage(
            ValueError,
            'Cannot provision a paid hotspot user without the customer phone number.',
        ):
            process_successful_payment(str(self.payment.id))

        sync_router.assert_not_called()

    def test_completed_payment_with_expired_entitlement_does_not_reactivate_customer(self):
        self.payment.status = 'COMPLETED'
        self.payment.paid_at = timezone.now() - timedelta(days=1)
        self.payment.save(update_fields=['status', 'paid_at', 'updated_at'])

        process_successful_payment(str(self.payment.id))

        customer = Customer.objects.get(tenant=self.tenant, username=self.payment.client_mac)
        recharge = Recharge.objects.get(transaction=self.payment)
        self.assertEqual(customer.status, Customer.Status.EXPIRED)
        self.assertLess(customer.expires_at, timezone.now())
        self.assertEqual(recharge.status, 'EXPIRED')
        radius_tables = set(connections['radius_db'].introspection.table_names())
        self.assertTrue(
            {'radcheck', 'radreply', 'radusergroup', 'radacct', 'nas'}.issubset(radius_tables)
        )

        username = self.payment.client_mac
        credential = RadCheck.objects.using('radius_db').get(
            username=username,
            attribute='Cleartext-Password',
        )
        self.assertEqual(credential.op, ':=')
        self.assertEqual(credential.value, username)
        self.assertEqual(
            RadReply.objects.using('radius_db').get(
                username=username,
                attribute='Session-Timeout',
            ).value,
            '2700',
        )
        self.assertEqual(
            RadReply.objects.using('radius_db').get(
                username=username,
                attribute='Mikrotik-Rate-Limit',
            ).value,
            '1024k/4096k',
        )

    def test_radius_write_failure_rolls_back_payment_and_partial_radius_changes(self):
        original_update_or_create = QuerySet.update_or_create

        def fail_on_rate_limit(queryset, **kwargs):
            if (
                queryset.model is RadReply
                and kwargs.get('attribute') == 'Mikrotik-Rate-Limit'
            ):
                raise OperationalError('simulated RADIUS write failure')
            return original_update_or_create(queryset, **kwargs)

        with patch.object(QuerySet, 'update_or_create', new=fail_on_rate_limit):
            with self.assertRaises(OperationalError):
                process_successful_payment(str(self.payment.id))

        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, 'PENDING')
        self.assertFalse(Customer.objects.filter(tenant=self.tenant).exists())
        self.assertFalse(Recharge.objects.filter(transaction=self.payment).exists())
        self.assertFalse(
            RadCheck.objects.using('radius_db').filter(
                username=self.payment.client_mac,
            ).exists()
        )
        self.assertFalse(
            RadReply.objects.using('radius_db').filter(
                username=self.payment.client_mac,
            ).exists()
        )


class PaidRouterProvisioningTests(SimpleTestCase):
    def setUp(self):
        self.router = SimpleNamespace(
            pk=42,
            type='mikrotik',
            is_online=False,
            nas_ip='192.0.2.10',
            nasname='test-router',
            api_port=8728,
        )
        self.plan = SimpleNamespace(
            name='Hourly',
            upload_speed_kbps=1024,
            download_speed_kbps=4096,
            simultaneous_devices=1,
            duration_minutes=60,
            limit_uptime='01:00:00',
        )

    @patch('librouteros.connect')
    @patch('apps.routers.services.resolve_router_credentials')
    def test_provisions_a_mac_bound_hotspot_user_using_resolved_credentials(
        self,
        resolve_credentials,
        connect,
    ):
        resolve_credentials.return_value = ('api-user', 'decrypted-password')
        connection = MagicMock()
        profile_path = MagicMock()
        user_path = MagicMock()
        profile_path.select.return_value.where.return_value = []
        user_path.select.return_value.where.return_value = []
        connection.path.side_effect = [profile_path, user_path]
        connect.return_value = connection

        with self.assertLogs('apps.billing.services', level='INFO') as logs:
            _sync_paid_user_to_router(
                self.router,
                self.plan,
                '+254712345678',
                '02:00:00:00:00:01',
            )

        resolve_credentials.assert_called_once_with(self.router)
        connect.assert_called_once_with(
            host='192.0.2.10',
            username='api-user',
            password='decrypted-password',
            port=8728,
            timeout=5,
        )
        profile_path.add.assert_called_once_with(
            name='Hourly',
            **{
                'rate-limit': '1024k/4096k',
                'shared-users': '1',
                'session-timeout': '01:00:00',
            },
        )
        user_path.add.assert_called_once_with(
            name='+254712345678',
            password='+254712345678',
            profile='Hourly',
            **{
                'limit-uptime': '01:00:00',
                'mac-address': '02:00:00:00:00:01',
            },
        )
        self.assertTrue(any(
            'Hotspot -> Users user +254712345678 was created' in message
            for message in logs.output
        ))
        connection.close.assert_called_once_with()

    @patch('librouteros.connect')
    @patch('apps.routers.services.resolve_router_credentials')
    def test_updates_hotspot_user_name_and_credentials(
        self,
        resolve_credentials,
        connect,
    ):
        resolve_credentials.return_value = ('api-user', 'decrypted-password')
        connection = MagicMock()
        profile_path = MagicMock()
        user_path = MagicMock()
        profile_path.select.return_value.where.return_value = [{'.id': '*1'}]
        user_path.select.return_value.where.return_value = [{'.id': '*2'}]
        connection.path.side_effect = [profile_path, user_path]
        connect.return_value = connection

        _sync_paid_user_to_router(self.router, self.plan, 'paid-user')

        user_path.set.assert_called_once_with(
            **{
                '.id': '*2',
                'name': 'paid-user',
                'password': 'paid-user',
                'profile': 'Hourly',
                'limit-uptime': '01:00:00',
            },
        )

    @patch('librouteros.connect', side_effect=TimeoutError('router unreachable'))
    @patch('apps.routers.services.resolve_router_credentials')
    def test_router_connection_failure_is_logged_and_does_not_raise(
        self,
        resolve_credentials,
        connect,
    ):
        resolve_credentials.return_value = ('api-user', 'decrypted-password')

        with self.assertLogs('apps.billing.services', level='WARNING') as logs:
            _sync_paid_user_to_router(self.router, self.plan, 'voucher-user')

        connect.assert_called_once()
        self.assertIn('RouterOS hotspot provisioning failed', logs.output[0])
        self.assertIn('router unreachable', logs.output[0])

    @patch('librouteros.connect')
    @patch('apps.routers.services.resolve_router_credentials')
    def test_rejects_ipv6_link_local_router_api_address(
        self,
        resolve_credentials,
        connect,
    ):
        self.router.nas_ip = 'fe80::1%ether1'
        resolve_credentials.return_value = ('api-user', 'decrypted-password')

        with self.assertLogs('apps.billing.services', level='WARNING') as logs:
            _sync_paid_user_to_router(self.router, self.plan, 'paid-user')

        connect.assert_not_called()
        self.assertIn('No valid IPv4 RouterOS API address', logs.output[0])

    @patch('librouteros.connect')
    @patch('apps.routers.services.resolve_router_credentials')
    def test_selects_an_ipv4_router_identity_instead_of_link_local_address(
        self,
        resolve_credentials,
        connect,
    ):
        self.router.nas_ip = 'fe80::1%ether1'
        self.router.nasname = '192.0.2.11'
        resolve_credentials.return_value = ('api-user', 'decrypted-password')
        connection = MagicMock()
        profile_path = MagicMock()
        user_path = MagicMock()
        profile_path.select.return_value.where.return_value = []
        user_path.select.return_value.where.return_value = []
        connection.path.side_effect = [profile_path, user_path]
        connect.return_value = connection

        _sync_paid_user_to_router(self.router, self.plan, 'paid-user')

        self.assertEqual(connect.call_args.kwargs['host'], '192.0.2.11')
