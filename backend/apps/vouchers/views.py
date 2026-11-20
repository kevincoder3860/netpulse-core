import secrets
import uuid
from decimal import Decimal
from datetime import timedelta
from django.db import transaction
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from core.permissions import (
    IsSuperAdminOrVendor, IsVendorCashier, IsVendorManager, IsVendorPlanViewer,
    tenant_for_user,
)
from apps.billing.models import Transaction
from apps.billing.services import process_successful_payment
from .models import Recharge, Voucher
from .serializers import RechargeSerializer, VoucherSerializer


class TenantScopedMixin:
    def get_queryset(self):
        queryset = super().get_queryset()
        if self.request.user.is_superadmin:
            tenant_id = self.request.query_params.get('tenant_id')
            return queryset.filter(tenant_id=tenant_id) if tenant_id else queryset
        tenant = tenant_for_user(self.request.user)
        return queryset.filter(tenant_id=tenant.id) if tenant else queryset.none()


class VoucherViewSet(TenantScopedMixin, viewsets.ModelViewSet):
    queryset = Voucher.objects.select_related('plan', 'router').order_by('-created_at')
    serializer_class = VoucherSerializer
    permission_classes = [IsSuperAdminOrVendor]

    def get_permissions(self):
        if self.action in ('list', 'retrieve'):
            return [IsVendorPlanViewer()]
        if self.action == 'redeem':
            return [AllowAny()]
        return [IsVendorManager()]

    def create(self, request, *args, **kwargs):
        count = min(max(int(request.data.get('count', 1)), 1), 1000)
        tenant_id = request.data.get('tenant') if request.user.is_superadmin else tenant_for_user(request.user).id
        created = []
        for _ in range(count):
            created.append(Voucher.objects.create(tenant_id=tenant_id, router_id=request.data.get('router'), plan_id=request.data.get('plan'), code=secrets.token_hex(4).upper(), expires_at=timezone.now() + timedelta(days=int(request.data.get('valid_days', 30)))))
        return Response(VoucherSerializer(created, many=True).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['post'], url_path='redeem', permission_classes=[AllowAny])
    def redeem(self, request):
        code = str(request.data.get('code', '')).strip().upper()
        mac = str(request.data.get('mac', '')).strip().upper()
        if not code or not mac:
            return Response({'detail': 'Voucher code and device MAC are required.'}, status=status.HTTP_400_BAD_REQUEST)
        if len(mac) != 17 or any(
            len(part) != 2 or any(char not in '0123456789ABCDEF' for char in part)
            for part in mac.split(':')
        ) or len(mac.split(':')) != 6:
            return Response({'detail': 'A valid device MAC address is required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                voucher = Voucher.objects.select_for_update().select_related('tenant', 'plan', 'router').get(code__iexact=code)
                if voucher.used_at:
                    return Response({'detail': 'Voucher has already been redeemed.'}, status=status.HTTP_400_BAD_REQUEST)
                if voucher.expires_at and voucher.expires_at <= timezone.now():
                    return Response({'detail': 'Voucher has expired.'}, status=status.HTTP_400_BAD_REQUEST)
                if voucher.tenant.status != 'ACTIVE' or not voucher.plan or not voucher.plan.is_active or not voucher.router:
                    return Response({'detail': 'Voucher package is unavailable.'}, status=status.HTTP_409_CONFLICT)

                transaction_record = Transaction.objects.create(
                    tenant=voucher.tenant,
                    nas=voucher.router,
                    plan=voucher.plan,
                    gross_amount=Decimal('0'),
                    platform_fee=Decimal('0'),
                    vendor_net_amount=Decimal('0'),
                    payment_method='VOUCHER',
                    phone_number='',
                    merchant_request_id=f'VOUCHER-{uuid.uuid4().hex}',
                    checkout_request_id=str(uuid.uuid4()),
                    client_mac=mac,
                )
                process_successful_payment(str(transaction_record.pk))
                voucher.assigned_mac = mac
                voucher.used_at = timezone.now()
                voucher.save(update_fields=['assigned_mac', 'used_at'])
        except Voucher.DoesNotExist:
            return Response({'detail': 'Voucher code was not found.'}, status=status.HTTP_404_NOT_FOUND)

        return Response({
            'success': True,
            'plan': voucher.plan.name,
            'duration_minutes': voucher.plan.duration_minutes,
            'message': f'Voucher {voucher.code} redeemed successfully.',
        })

    @action(detail=False, methods=['delete'], url_path='delete-used')
    def delete_used(self, request):
        deleted, _ = self.get_queryset().filter(used_at__isnull=False).delete()
        return Response({'deleted': deleted})


class RechargeViewSet(TenantScopedMixin, viewsets.ReadOnlyModelViewSet):
    queryset = Recharge.objects.select_related('plan', 'router').order_by('-created_at')
    serializer_class = RechargeSerializer
    permission_classes = [IsVendorCashier]
