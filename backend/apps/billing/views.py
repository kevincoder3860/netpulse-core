from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from rest_framework import generics, serializers, status, viewsets
from rest_framework.throttling import ScopedRateThrottle
from django.db import DatabaseError, transaction
from django.db.models import Q
from django.urls import reverse
from django.conf import settings
from django.core.cache import cache
from decimal import Decimal
import uuid
import logging
from .models import (
    BlockedSTKNumber, CommissionRecord, HotspotPlan, MpesaGatewayConfiguration,
    SalesAgent, Transaction,
)
from apps.routers.models import NAS
from .serializers import (
    BlockedSTKNumberSerializer, CommissionRecordSerializer, SalesAgentSerializer,
    TransactionSerializer, TransactionStatusSerializer,
)
from .serializers import HotspotPlanSerializer
from core.permissions import (
    IsCustomer, IsSuperAdminOrVendor, IsVendorCashier, IsVendorManager,
    IsVendorPlanViewer, tenant_for_user,
)
from apps.plans.utils import sync_hotspot_plan_to_mikrotik
from apps.billing.mpesa import MpesaGatewayError, initiate_stk_push, query_stk_status
from apps.billing.paystack import (
    PaystackGatewayError,
    initiate_mobile_money_charge,
    verify_mobile_money_charge,
    verify_webhook_signature,
)

logger = logging.getLogger(__name__)


def _mpesa_gateway_error_response(exc):
    response_data = {
        'detail': str(exc),
        'code': exc.code,
    }
    if exc.gateway_status is not None:
        response_data['gateway_status'] = exc.gateway_status
    if exc.provider_error_code:
        response_data['provider_error_code'] = exc.provider_error_code

    response_status = (
        status.HTTP_400_BAD_REQUEST
        if exc.gateway_status is not None and 400 <= exc.gateway_status < 500
        else status.HTTP_502_BAD_GATEWAY
    )
    return Response(response_data, status=response_status)


def _paystack_gateway_error_response(exc):
    response_status = (
        status.HTTP_400_BAD_REQUEST
        if exc.code in {'INVALID_PHONE_NUMBER', 'INVALID_PAYMENT_AMOUNT'}
        else status.HTTP_503_SERVICE_UNAVAILABLE
        if exc.code in {'PAYSTACK_NOT_CONFIGURED', 'PAYSTACK_EMAIL_REQUIRED', 'INVALID_PAYSTACK_CONFIGURATION'}
        else status.HTTP_502_BAD_GATEWAY
    )
    response_data = {'detail': str(exc), 'code': exc.code}
    if exc.gateway_status is not None:
        response_data['gateway_status'] = exc.gateway_status
    return Response(
        response_data,
        status=response_status,
    )


def _paystack_charge_matches(payment, data):
    try:
        amount = int(data.get('amount'))
    except (TypeError, ValueError):
        return False
    expected_amount = int(round(payment.gross_amount * 100))
    return (
        data.get('reference') == payment.checkout_request_id
        and str(data.get('currency', '')).upper() == 'KES'
        and amount == expected_amount
    )


class MpesaGatewayConfigurationView(APIView):
    permission_classes = [IsVendorManager]

    @staticmethod
    def _response(configuration):
        if not configuration:
            return {
                'configured': False,
                'environment': 'sandbox',
                'merchant_type': MpesaGatewayConfiguration.MerchantType.PAYBILL,
                'shortcode': '',
                'consumer_key_set': False,
                'consumer_secret_set': False,
                'passkey_set': False,
            }
        return {
            'configured': configuration.is_configured,
            'environment': configuration.environment,
            'merchant_type': configuration.merchant_type,
            'shortcode': configuration.shortcode,
            'consumer_key_set': bool(configuration.consumer_key_encrypted),
            'consumer_secret_set': bool(configuration.consumer_secret_encrypted),
            'passkey_set': bool(configuration.passkey_encrypted),
        }

    def get(self, request):
        tenant = tenant_for_user(request.user)
        if not tenant:
            return Response({'detail': 'A vendor workspace is required.'}, status=status.HTTP_400_BAD_REQUEST)
        configuration = getattr(tenant, 'mpesa_gateway', None)
        return Response(self._response(configuration))

    def put(self, request):
        class ConfigurationSerializer(serializers.Serializer):
            environment = serializers.ChoiceField(
                choices=MpesaGatewayConfiguration.Environment.choices,
                required=False,
            )
            merchant_type = serializers.ChoiceField(
                choices=MpesaGatewayConfiguration.MerchantType.choices,
                required=False,
            )
            shortcode = serializers.RegexField(r'^\d{5,7}$', required=False)
            consumer_key = serializers.CharField(max_length=512, required=False, allow_blank=True, trim_whitespace=True)
            consumer_secret = serializers.CharField(max_length=512, required=False, allow_blank=True, trim_whitespace=True)
            passkey = serializers.CharField(max_length=1024, required=False, allow_blank=True, trim_whitespace=True)

        payload = ConfigurationSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        tenant = tenant_for_user(request.user)
        if not tenant:
            return Response({'detail': 'A vendor workspace is required.'}, status=status.HTTP_400_BAD_REQUEST)
        values = payload.validated_data
        with transaction.atomic():
            configuration = MpesaGatewayConfiguration.objects.filter(tenant=tenant).first()
            if not values:
                return Response(self._response(configuration))
            if configuration is None:
                configuration, _ = MpesaGatewayConfiguration.objects.get_or_create(
                    tenant=tenant,
                    defaults={
                        'shortcode': '',
                        'consumer_key_encrypted': '',
                        'consumer_secret_encrypted': '',
                        'passkey_encrypted': '',
                    },
                )
            for field in ('environment', 'merchant_type', 'shortcode'):
                if field in values:
                    setattr(configuration, field, values[field])
            configuration.set_credentials(
                consumer_key=values.get('consumer_key'),
                consumer_secret=values.get('consumer_secret'),
                passkey=values.get('passkey'),
            )
            configuration.save()
            cache.delete(f'mpesa-access-token-{configuration.pk}-{configuration.environment}')
        return Response(self._response(configuration))

class BillingScopedViewSet(viewsets.ModelViewSet):
    permission_classes = [IsSuperAdminOrVendor]

    def get_permissions(self):
        if self.action in ('list', 'retrieve'):
            return [IsVendorCashier()]
        return [IsVendorManager()]

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.request.user.is_superadmin:
            tenant_id = self.request.query_params.get('tenant_id')
            return queryset.filter(tenant_id=tenant_id) if tenant_id else queryset
        tenant = tenant_for_user(self.request.user)
        return queryset.filter(tenant_id=tenant.id) if tenant else queryset.none()


class BlockedSTKNumberViewSet(BillingScopedViewSet):
    queryset = BlockedSTKNumber.objects.all().order_by('-created_at')
    serializer_class = BlockedSTKNumberSerializer


class SalesAgentViewSet(BillingScopedViewSet):
    queryset = SalesAgent.objects.all().order_by('name')
    serializer_class = SalesAgentSerializer


class CommissionRecordViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = CommissionRecord.objects.select_related('agent', 'transaction').all().order_by('-created_at')
    serializer_class = CommissionRecordSerializer
    permission_classes = [IsVendorCashier]

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.request.user.is_superadmin:
            return queryset
        tenant = tenant_for_user(self.request.user)
        return queryset.filter(agent__tenant_id=tenant.id) if tenant else queryset.none()


class HotspotPlanViewSet(viewsets.ModelViewSet):
    queryset = HotspotPlan.objects.all().order_by('-created_at')
    serializer_class = HotspotPlanSerializer
    permission_classes = [IsVendorPlanViewer]

    def get_permissions(self):
        if getattr(self.request.user, 'customer_profile', None) and self.action in ('list', 'retrieve'):
            return [IsCustomer()]
        return [IsVendorManager()] if self.action in ('create', 'update', 'partial_update', 'destroy') else [IsVendorPlanViewer()]

    def get_queryset(self):
        queryset = super().get_queryset()
        tenant_id = self.request.query_params.get('tenant_id')
        if tenant_id:
            try:
                tenant_id = uuid.UUID(tenant_id)
            except (ValueError, TypeError, AttributeError):
                return queryset.none()

        if self.request.user.is_superadmin:
            if tenant_id:
                queryset = queryset.filter(tenant_id=tenant_id)
        else:
            tenant = tenant_for_user(self.request.user)
            queryset = queryset.filter(tenant_id=tenant.id) if tenant else queryset.none()
            if tenant_id and (not tenant or tenant.id != tenant_id):
                return queryset.none()
        if self.request.query_params.get('is_active') is not None:
            queryset = queryset.filter(is_active=self.request.query_params['is_active'].lower() == 'true')
        return queryset

    def update(self, request, *args, **kwargs):
        print(f"--> RECEIVED UPDATE REQUEST FOR PLAN ID: {kwargs.get('pk')}")
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        print(f"--> RECEIVED UPDATE REQUEST FOR PLAN ID: {kwargs.get('pk')}")
        return super().partial_update(request, *args, **kwargs)

    def perform_create(self, serializer):
        new_plan = serializer.save()
        sync_hotspot_plan_to_mikrotik(new_plan)
        try:
            from apps.billing.services import sync_hotspot_plan_profile_to_routers
            sync_hotspot_plan_profile_to_routers(new_plan, action='create')
        except Exception:
            pass

    def perform_update(self, serializer):
        instance = self.get_object()
        old_name = instance.name
        updated_plan = serializer.save()
        sync_hotspot_plan_to_mikrotik(updated_plan, old_name=old_name)
        try:
            from apps.billing.services import sync_hotspot_plan_profile_to_routers
            sync_hotspot_plan_profile_to_routers(updated_plan, action='update', old_name=old_name)
        except Exception:
            pass

    def perform_destroy(self, instance):
        instance.is_active = False
        sync_hotspot_plan_to_mikrotik(instance)
        try:
            from apps.billing.services import sync_hotspot_plan_profile_to_routers
            sync_hotspot_plan_profile_to_routers(instance, action='delete')
        except Exception:
            pass
        instance.delete()

class CreateHotspotPlanView(APIView):
    permission_classes = [IsVendorManager]

    def post(self, request):
        print('INCOMING PAYLOAD:', request.data)
        try:
            tenant = tenant_for_user(request.user)
            if not tenant:
                return Response({'success': False, 'message': 'A vendor tenant is required.'}, status=status.HTTP_400_BAD_REQUEST)

            payload = request.data.copy()
            submitted_tenant_id = payload.get('tenant_id') or payload.get('tenant')
            if not submitted_tenant_id:
                raise ValueError('tenant_id is required.')
            try:
                submitted_tenant_id = uuid.UUID(str(submitted_tenant_id))
            except (ValueError, TypeError, AttributeError) as exc:
                raise ValueError('tenant_id must be a valid UUID.') from exc
            if submitted_tenant_id != tenant.id:
                raise ValueError('tenant_id does not belong to the authenticated vendor.')
            payload['tenant'] = tenant.id
            payload['price'] = float(payload.get('price', 0))
            payload['duration_minutes'] = int(payload.get('duration_minutes', 60))
            payload['download_speed_kbps'] = int(payload.get('download_speed_kbps', 2048))
            payload['upload_speed_kbps'] = int(payload.get('upload_speed_kbps', 1024))
            payload['simultaneous_devices'] = int(payload.get('simultaneous_devices', 1))
            if payload['duration_minutes'] <= 0 or payload['download_speed_kbps'] <= 0 or payload['upload_speed_kbps'] <= 0 or payload['simultaneous_devices'] <= 0:
                raise ValueError('Duration, bandwidth, and simultaneous devices must be positive integers.')

            serializer = HotspotPlanSerializer(data=payload)
            if not serializer.is_valid():
                logger.warning('Invalid hotspot plan payload: %s; data=%s', serializer.errors, request.data)
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            save_kwargs = {'currency': 'KES'} if hasattr(HotspotPlan, 'currency') else {}
            plan = serializer.save(**save_kwargs)

            sync_hotspot_plan_to_mikrotik(plan)
            try:
                from apps.billing.services import sync_hotspot_plan_profile_to_routers
                sync_hotspot_plan_profile_to_routers(plan, action='create')
            except Exception:
                pass

            response = {'success': True, 'message': 'Plan created successfully'}
            return Response(response, status=status.HTTP_201_CREATED)
        except (ValueError, TypeError, DatabaseError, serializers.ValidationError) as exc:
            logger.warning('Hotspot plan creation failed: %s', exc)
            return Response({'success': False, 'message': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            logger.exception('Unexpected hotspot plan creation failure')
            return Response({'success': False, 'message': str(exc)}, status=status.HTTP_400_BAD_REQUEST)


class TransactionViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Transaction.objects.all().order_by('-created_at')
    serializer_class = TransactionSerializer
    permission_classes = [IsVendorCashier]

    def get_permissions(self):
        if getattr(self.request.user, 'customer_profile', None):
            return [IsCustomer()]
        return super().get_permissions()

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.request.user.is_superadmin:
            if self.request.query_params.get('tenant_id'):
                queryset = queryset.filter(tenant_id=self.request.query_params['tenant_id'])
        else:
            tenant = tenant_for_user(self.request.user)
            queryset = queryset.filter(tenant_id=tenant.id) if tenant else queryset.none()
            customer = getattr(self.request.user, 'customer_profile', None)
            if customer:
                queryset = queryset.filter(
                    tenant_id=customer.tenant_id,
                ).filter(
                    Q(phone_number=customer.phone_number) | Q(client_mac__iexact=customer.mac_address)
                )
        if self.request.query_params.get('status'):
            queryset = queryset.filter(status=self.request.query_params['status'].upper())
        return queryset

class PaystackStkPushView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'paystack_stk'

    def post(self, request):
        class InitiateSerializer(serializers.Serializer):
            tenant_id = serializers.UUIDField()
            plan_id = serializers.IntegerField(min_value=1)
            phone_number = serializers.CharField(max_length=32)
            nas_id = serializers.IntegerField(min_value=1, required=False)
            mac_address = serializers.RegexField(
                r'^(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$',
                required=False,
                allow_blank=True,
            )

        payload = InitiateSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        values = payload.validated_data
        try:
            plan = HotspotPlan.objects.select_related('tenant').get(
                id=values['plan_id'],
                tenant_id=values['tenant_id'],
            )
        except HotspotPlan.DoesNotExist:
            return Response(
                {'detail': 'The selected plan does not belong to this vendor.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        tenant = plan.tenant
        if tenant.status != 'ACTIVE' or not plan.is_active:
            return Response(
                {'detail': 'This hotspot account or plan is unavailable.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        nas = None
        if values.get('nas_id') is not None:
            try:
                nas = NAS.objects.get(id=values['nas_id'], tenant_id=tenant.id)
            except NAS.DoesNotExist:
                return Response(
                    {'detail': 'The selected router does not belong to this vendor.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        try:
            provider_response = initiate_mobile_money_charge(
                tenant,
                phone_number=values['phone_number'],
                amount=plan.price,
            )
        except PaystackGatewayError as exc:
            return _paystack_gateway_error_response(exc)

        commission = Decimal(tenant.platform_commission_pct)
        fee = (plan.price * commission / Decimal('100')).quantize(Decimal('0.01'))
        reference = provider_response['reference']
        with transaction.atomic():
            payment = Transaction.objects.create(
                tenant=tenant,
                nas=nas,
                plan=plan,
                gross_amount=plan.price,
                platform_fee=fee,
                vendor_net_amount=plan.price - fee,
                phone_number=provider_response['phone_number'],
                merchant_request_id=reference,
                checkout_request_id=reference,
                client_mac=values.get('mac_address') or provider_response['phone_number'],
                payment_method='PAYSTACK_MOBILE_MONEY',
                status='PENDING',
            )

        return Response(
            {
                'message': provider_response['message'],
                'reference': reference,
                'checkout_request_id': payment.checkout_request_id,
                'amount': float(plan.price),
                'amount_cents': provider_response['amount_cents'],
            },
            status=status.HTTP_201_CREATED,
        )


class PaystackWebhookView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        raw_body = request.body
        payload = request.data
        if not isinstance(payload, dict):
            return Response({'detail': 'Invalid Paystack webhook payload.'}, status=status.HTTP_400_BAD_REQUEST)
        if payload.get('event') != 'charge.success':
            return Response({'status': 'ignored'}, status=status.HTTP_200_OK)

        data = payload.get('data')
        reference = data.get('reference') if isinstance(data, dict) else None
        if not isinstance(reference, str) or not reference:
            return Response({'detail': 'Paystack charge event is missing its reference.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            payment = Transaction.objects.select_related('tenant').get(
                checkout_request_id=reference,
                payment_method='PAYSTACK_MOBILE_MONEY',
            )
        except Transaction.DoesNotExist:
            return Response({'status': 'ignored'}, status=status.HTTP_200_OK)

        try:
            signature_valid = verify_webhook_signature(
                payment.tenant,
                raw_body,
                request.headers.get('x-paystack-signature', ''),
            )
        except PaystackGatewayError:
            logger.exception('Could not verify Paystack webhook for transaction %s', payment.pk)
            return Response(
                {'detail': 'Paystack webhook verification is temporarily unavailable.'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        if not signature_valid:
            return Response({'detail': 'Invalid Paystack signature.'}, status=status.HTTP_401_UNAUTHORIZED)
        if (
            not isinstance(data, dict)
            or str(data.get('status', '')).lower() != 'success'
            or not _paystack_charge_matches(payment, data)
        ):
            logger.warning('Paystack charge did not match transaction %s', payment.pk)
            return Response({'detail': 'Paystack charge does not match the pending transaction.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            from apps.billing.services import process_successful_payment
            process_successful_payment(str(payment.id), provider_data=data)
        except Exception:
            logger.exception('Verified Paystack payment could not be provisioned')
            return Response(
                {'detail': 'Payment is verified but hotspot access could not be provisioned yet.'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response({'status': 'accepted'}, status=status.HTTP_200_OK)


class InitiatePaymentView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'mpesa_stk'

    def post(self, request):
        class InitiateSerializer(serializers.Serializer):
            nas_id = serializers.IntegerField(min_value=1)
            plan_id = serializers.IntegerField(min_value=1)
            phone_number = serializers.RegexField(r'^254[17]\d{8}$')
            amount = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
            mac_address = serializers.RegexField(
                r'^(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$',
                required=False,
                allow_blank=True,
            )

        payload = InitiateSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            nas = NAS.objects.select_related('tenant').get(id=payload.validated_data['nas_id'])
            plan = HotspotPlan.objects.select_related('tenant').get(id=payload.validated_data['plan_id'])
        except (NAS.DoesNotExist, HotspotPlan.DoesNotExist):
            return Response({'detail': 'Invalid router or plan.'}, status=status.HTTP_400_BAD_REQUEST)

        if nas.tenant.status != 'ACTIVE' or not plan.is_active:
            return Response({"error": "This hotspot account or plan is unavailable."}, status=403)
        if plan.tenant_id != nas.tenant_id:
            return Response({"error": "The selected plan does not belong to this router's tenant."}, status=400)
        if 'amount' in payload.validated_data and payload.validated_data['amount'] != plan.price:
            return Response(
                {'detail': 'The amount does not match the selected plan price.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            configuration = plan.tenant.mpesa_gateway
        except MpesaGatewayConfiguration.DoesNotExist:
            return Response(
                {'detail': 'M-Pesa is not configured for this hotspot.'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        if not configuration.is_configured:
            return Response(
                {'detail': 'M-Pesa credentials are incomplete for this hotspot.'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        if plan.price <= 0 or plan.price != plan.price.to_integral_value():
            return Response(
                {'detail': 'The selected plan price must be a positive whole number of KES for M-Pesa.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        phone_number = payload.validated_data['phone_number']
        amount = int(plan.price)
        commission = Decimal(nas.tenant.platform_commission_pct)
        fee = (plan.price * commission / Decimal('100')).quantize(Decimal('0.01'))
        callback_url = settings.MPESA_CALLBACK_URL or request.build_absolute_uri(reverse('mpesa-callback'))
        if configuration.environment == MpesaGatewayConfiguration.Environment.PRODUCTION and not callback_url.startswith('https://'):
            return Response(
                {'detail': 'Set MPESA_CALLBACK_URL to the public HTTPS callback endpoint before using production Daraja.'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        try:
            provider_response = initiate_stk_push(
                configuration,
                phone_number=phone_number,
                amount=amount,
                reference=plan.name,
                callback_url=callback_url,
            )
        except MpesaGatewayError as exc:
            return _mpesa_gateway_error_response(exc)
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        with transaction.atomic():
            payment = Transaction.objects.create(
                tenant=nas.tenant,
                nas=nas,
                plan=plan,
                gross_amount=plan.price,
                platform_fee=fee,
                vendor_net_amount=plan.price - fee,
                phone_number=phone_number,
                merchant_request_id=provider_response['merchant_request_id'],
                checkout_request_id=provider_response['checkout_request_id'],
                client_mac=payload.validated_data.get('mac_address') or phone_number,
                status='PENDING',
            )

        return Response({
            'message': provider_response['message'],
            'checkout_request_id': payment.checkout_request_id,
            'amount': amount,
        }, status=status.HTTP_201_CREATED)

class MpesaCallbackView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        body = request.data.get('Body')
        callback = body.get('stkCallback') if isinstance(body, dict) else None
        if not isinstance(callback, dict) or not isinstance(callback.get('CheckoutRequestID'), str):
            return Response(
                {'detail': 'Invalid M-Pesa callback payload.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        from apps.billing.tasks import process_mpesa_callback_task
        result = process_mpesa_callback_task.apply(args=(request.data,), throw=True)
        if result.result == 'retry':
            return Response(
                {'detail': 'M-Pesa callback could not be verified. Daraja may retry this callback.'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response({'ResultCode': 0, 'ResultDesc': 'Accepted'}, status=status.HTTP_200_OK)

class TransactionStatusView(generics.RetrieveAPIView):
    permission_classes = [AllowAny]
    queryset = Transaction.objects.all()
    serializer_class = TransactionStatusSerializer
    lookup_field = 'checkout_request_id'

    def retrieve(self, request, *args, **kwargs):
        payment = self.get_object()
        if payment.status == 'PENDING':
            if payment.payment_method == 'PAYSTACK_MOBILE_MONEY':
                try:
                    provider_status = verify_mobile_money_charge(
                        payment.tenant,
                        payment.checkout_request_id,
                    )
                except PaystackGatewayError as exc:
                    return _paystack_gateway_error_response(exc)
                if not _paystack_charge_matches(payment, provider_status):
                    logger.warning('Paystack verification did not match transaction %s', payment.pk)
                    return Response(
                        {'detail': 'Paystack transaction details did not match the pending payment.'},
                        status=status.HTTP_502_BAD_GATEWAY,
                    )
                charge_status = str(provider_status.get('status', '')).lower()
                if charge_status == 'success':
                    try:
                        from apps.billing.services import process_successful_payment
                        payment = process_successful_payment(
                            str(payment.id),
                            provider_data=provider_status,
                        )
                    except Exception:
                        logger.exception('Verified Paystack payment could not be provisioned')
                        return Response(
                            {'detail': 'Payment is verified but hotspot access could not be provisioned yet.'},
                            status=status.HTTP_503_SERVICE_UNAVAILABLE,
                        )
                elif charge_status in {'failed', 'abandoned'}:
                    payment.status = 'FAILED'
                    payment.save(update_fields=['status', 'updated_at'])
            else:
                try:
                    configuration = payment.tenant.mpesa_gateway
                except MpesaGatewayConfiguration.DoesNotExist:
                    configuration = None
                if configuration and configuration.is_configured:
                    try:
                        provider_status = query_stk_status(configuration, payment.checkout_request_id)
                    except MpesaGatewayError as exc:
                        return _mpesa_gateway_error_response(exc)
                    except ValueError as exc:
                        return Response({'detail': str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
                    if str(provider_status.get('ResponseCode')) == '0' and provider_status.get('ResultCode') is not None:
                        if str(provider_status['ResultCode']) == '0':
                            try:
                                from apps.billing.services import process_successful_payment
                                payment = process_successful_payment(str(payment.id))
                            except Exception:
                                logger.exception('Verified M-Pesa payment could not be provisioned')
                                return Response(
                                    {'detail': 'Payment is verified but hotspot access could not be provisioned yet.'},
                                    status=status.HTTP_503_SERVICE_UNAVAILABLE,
                                )
                        else:
                            payment.status = 'FAILED'
                            payment.save(update_fields=['status', 'updated_at'])
        return Response(self.get_serializer(payment).data)
