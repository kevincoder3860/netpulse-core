from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework import generics, serializers, status, viewsets
from django.db import DatabaseError
import uuid
import logging
from .models import BlockedSTKNumber, CommissionRecord, SalesAgent, Transaction, HotspotPlan
from apps.routers.models import NAS
from .serializers import BlockedSTKNumberSerializer, CommissionRecordSerializer, SalesAgentSerializer, TransactionSerializer
from .serializers import HotspotPlanSerializer
from .tasks import process_mpesa_callback_task
from core.permissions import IsSuperAdminOrVendor, IsVendorCashier, IsVendorManager, IsVendorPlanViewer, tenant_for_user

logger = logging.getLogger(__name__)


class BillingScopedViewSet(viewsets.ModelViewSet):
    permission_classes = [IsSuperAdminOrVendor]
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
    permission_classes = [IsSuperAdminOrVendor]

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

    def list(self, request, *args, **kwargs):
        try:
            return super().list(request, *args, **kwargs)
        except (ValueError, TypeError) as exc:
            logger.warning('Invalid plan tenant filter %r: %s', request.query_params.get('tenant_id'), exc)
            return Response([], status=status.HTTP_200_OK)
        except Exception:
            logger.exception('Unable to load hotspot plans for tenant_id=%r', request.query_params.get('tenant_id'))
            return Response([], status=status.HTTP_200_OK)


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
            rate_limit = f'{plan.upload_speed_kbps}k/{plan.download_speed_kbps}k'
            sync_warnings = []

            for router in NAS.objects.filter(tenant=tenant, is_online=True, type='mikrotik'):
                try:
                    from librouteros import connect
                    connection = connect(
                        host=router.nas_ip,
                        username=router.api_username,
                        password=router.api_password,
                        port=router.api_port or 8728,
                    )
                    try:
                        connection.path('/ip/hotspot/user/profile').add(
                            name=plan.name,
                            **{'rate-limit': rate_limit, 'shared-users': str(plan.simultaneous_devices)},
                        )
                    finally:
                        connection.close()
                except Exception as exc:
                    sync_warnings.append(f'{router.nasname}: {exc}')
                    logger.exception('Unable to provision plan %s to router %s', plan.pk, router.pk)

            response = {'success': True, 'message': 'Plan created successfully'}
            if sync_warnings:
                response['sync_warning'] = 'Plan saved, but some routers could not be synchronized.'
                response['sync_warnings'] = sync_warnings
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

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.request.user.is_superadmin:
            if self.request.query_params.get('tenant_id'):
                queryset = queryset.filter(tenant_id=self.request.query_params['tenant_id'])
        else:
            tenant = tenant_for_user(self.request.user)
            queryset = queryset.filter(tenant_id=tenant.id) if tenant else queryset.none()
        if self.request.query_params.get('status'):
            queryset = queryset.filter(status=self.request.query_params['status'].upper())
        return queryset

class InitiatePaymentView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        # 1. Extract payment data
        nas_id = request.data.get('nas_id')
        plan_id = request.data.get('plan_id')
        phone_number = request.data.get('phone_number')
        mac_address = request.data.get('mac_address')

        try:
            nas = NAS.objects.get(id=nas_id)
            plan = HotspotPlan.objects.get(id=plan_id)
        except (NAS.DoesNotExist, HotspotPlan.DoesNotExist):
            return Response({"error": "Invalid NAS or Plan ID"}, status=400)

        if nas.tenant.status != 'ACTIVE' or not plan.is_active:
            return Response({"error": "This hotspot account or plan is unavailable."}, status=403)

        # 2. Setup Transaction object
        checkout_request_id = str(uuid.uuid4()) # Dummy ID until real M-Pesa is integrated
        merchant_request_id = str(uuid.uuid4())

        # Fee calculations
        platform_fee = plan.price * (nas.tenant.platform_commission_pct / 100)
        vendor_net_amount = plan.price - platform_fee

        txn = Transaction.objects.create(
            tenant=nas.tenant,
            nas=nas,
            plan=plan,
            gross_amount=plan.price,
            platform_fee=platform_fee,
            vendor_net_amount=vendor_net_amount,
            phone_number=phone_number,
            client_mac=mac_address,
            merchant_request_id=merchant_request_id,
            checkout_request_id=checkout_request_id,
            status='PENDING'
        )

        # 3. Here you would trigger Daraja API STK Push using the checkout_request_id
        # ...
        
        return Response({
            "message": "Payment initiated successfully",
            "checkout_request_id": checkout_request_id
        })

class MpesaCallbackView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        try:
            # 1. Immediately dispatch Celery task
            process_mpesa_callback_task.delay(request.data)
        except Exception:
            logger.exception("Failed to dispatch M-Pesa callback task")
        
        # 2. Acknowledge receipt to Safaricom Daraja API
        return Response({
            "ResultCode": 0,
            "ResultDesc": "Accepted"
        }, status=200)

class TransactionStatusView(generics.RetrieveAPIView):
    permission_classes = [AllowAny]
    queryset = Transaction.objects.all()
    serializer_class = TransactionSerializer
    lookup_field = 'checkout_request_id'
