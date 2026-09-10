import secrets
from datetime import timedelta
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from core.permissions import IsSuperAdminOrVendor, tenant_for_user
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

    def create(self, request, *args, **kwargs):
        count = min(max(int(request.data.get('count', 1)), 1), 1000)
        tenant_id = request.data.get('tenant') if request.user.is_superadmin else tenant_for_user(request.user).id
        created = []
        for _ in range(count):
            created.append(Voucher.objects.create(tenant_id=tenant_id, router_id=request.data.get('router'), plan_id=request.data.get('plan'), code=secrets.token_hex(4).upper(), expires_at=timezone.now() + timedelta(days=int(request.data.get('valid_days', 30)))))
        return Response(VoucherSerializer(created, many=True).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['delete'], url_path='delete-used')
    def delete_used(self, request):
        deleted, _ = self.get_queryset().filter(used_at__isnull=False).delete()
        return Response({'deleted': deleted})


class RechargeViewSet(TenantScopedMixin, viewsets.ReadOnlyModelViewSet):
    queryset = Recharge.objects.select_related('plan', 'router').order_by('-created_at')
    serializer_class = RechargeSerializer
    permission_classes = [IsSuperAdminOrVendor]
