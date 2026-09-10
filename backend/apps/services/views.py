from rest_framework import viewsets
from core.permissions import IsSuperAdminOrVendor, tenant_for_user
from .models import BurstProfile, FUPProfile
from .serializers import BurstProfileSerializer, FUPProfileSerializer


class ScopedViewSet(viewsets.ModelViewSet):
    permission_classes = [IsSuperAdminOrVendor]
    def get_queryset(self):
        queryset = super().get_queryset()
        if self.request.user.is_superadmin:
            tenant_id = self.request.query_params.get('tenant_id')
            return queryset.filter(tenant_id=tenant_id) if tenant_id else queryset
        tenant = tenant_for_user(self.request.user)
        return queryset.filter(tenant_id=tenant.id) if tenant else queryset.none()


class BurstProfileViewSet(ScopedViewSet):
    queryset = BurstProfile.objects.all().order_by('name')
    serializer_class = BurstProfileSerializer


class FUPProfileViewSet(ScopedViewSet):
    queryset = FUPProfile.objects.all().order_by('name')
    serializer_class = FUPProfileSerializer
