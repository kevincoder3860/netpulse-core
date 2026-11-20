from rest_framework import viewsets
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.permissions import AllowAny
from rest_framework import status
from datetime import timedelta
from django.contrib.auth import get_user_model
from django.db.models import Sum
from django.utils import timezone
from rest_framework_simplejwt.tokens import AccessToken
from .models import AuditLog, Tenant, TenantStaff, TenantUser
from .serializers import (
    RegisterSerializer, StaffInviteSerializer, StaffSerializer,
    TenantBrandingSerializer, TenantSerializer,
)
from .permissions import IsSuperAdmin, IsVendorMember, IsVendorOwner
from core.permissions import IsCustomer, is_superadmin_user


class RegisterView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(serializer.save(), status=status.HTTP_201_CREATED)


class TenantViewSet(viewsets.ModelViewSet):
    queryset = Tenant.objects.all().order_by('-created_at')
    serializer_class = TenantSerializer
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        user = self.request.user
        if is_superadmin_user(user):
            return [IsSuperAdmin()]
        profile = getattr(self.request.user, 'tenant_profile', None)
        if profile and profile.role == TenantUser.Role.VENDOR:
            if self.action in ('list', 'retrieve', 'partial_update'):
                return [IsVendorOwner()]
            return [IsSuperAdmin()]
        if getattr(user, 'customer_profile', None):
            return [IsCustomer()] if self.action in ('list', 'retrieve') else [IsSuperAdmin()]
        staff = getattr(user, 'staff_profile', None)
        if staff:
            return [IsVendorMember()] if self.action in ('list', 'retrieve') else [IsSuperAdmin()]
        return [IsSuperAdmin()]

    def get_serializer_class(self):
        profile = getattr(self.request.user, 'tenant_profile', None)
        if (
            profile
            and profile.role == TenantUser.Role.VENDOR
            and self.action == 'partial_update'
        ):
            return TenantBrandingSerializer
        return TenantSerializer

    def get_queryset(self):
        user = self.request.user
        if is_superadmin_user(user):
            return self.queryset
        profile = getattr(self.request.user, 'tenant_profile', None)
        if profile and profile.role == TenantUser.Role.VENDOR:
            return self.queryset.filter(id=profile.tenant_id)
        staff = getattr(user, 'staff_profile', None)
        if staff and staff.is_active:
            return self.queryset.filter(id=staff.tenant_id)
        customer = getattr(user, 'customer_profile', None)
        if customer and not profile and not staff:
            return self.queryset.filter(id=customer.tenant_id)
        return self.queryset.none()


class VendorStaffView(APIView):
    permission_classes = [IsVendorOwner]

    def get(self, request):
        tenant = request.user.tenant_profile.tenant
        return Response(StaffSerializer(tenant.staff.select_related('user'), many=True).data)

    def post(self, request):
        tenant = request.user.tenant_profile.tenant
        serializer = StaffInviteSerializer(data=request.data, context={'tenant': tenant})
        serializer.is_valid(raise_exception=True)
        staff = serializer.save()
        return Response(StaffSerializer(staff).data, status=status.HTTP_201_CREATED)


class VendorStaffDetailView(APIView):
    permission_classes = [IsVendorOwner]

    def patch(self, request, staff_id):
        staff = TenantStaff.objects.get(id=staff_id, tenant=request.user.tenant_profile.tenant)
        if 'role' in request.data:
            staff.role = request.data['role']
        if 'is_active' in request.data:
            staff.is_active = bool(request.data['is_active'])
        staff.save(update_fields=['role', 'is_active'])
        return Response(StaffSerializer(staff).data)

    def delete(self, request, staff_id):
        staff = TenantStaff.objects.get(id=staff_id, tenant=request.user.tenant_profile.tenant)
        staff.user.is_active = False
        staff.user.save(update_fields=['is_active'])
        staff.is_active = False
        staff.save(update_fields=['is_active'])
        return Response(status=status.HTTP_204_NO_CONTENT)


class SuperAdminTenantActionView(APIView):
    permission_classes = [IsSuperAdmin]

    def post(self, request, tenant_id, action):
        tenant = Tenant.objects.get(id=tenant_id)
        if action not in ('suspend', 'close', 'impersonate'):
            return Response({'detail': 'Unknown action.'}, status=status.HTTP_404_NOT_FOUND)
        if action == 'impersonate':
            token = AccessToken.for_user(request.user)
            token['role'] = 'SUPERADMIN'
            token['tenant_id'] = str(tenant.id)
            token['impersonated_tenant_id'] = str(tenant.id)
            token['read_only'] = True
            AuditLog.objects.create(actor=request.user, tenant=tenant, action='IMPERSONATE', metadata={'read_only': True})
            return Response({'access': str(token), 'tenant_id': str(tenant.id), 'read_only': True})
        new_status = Tenant.Status.SUSPENDED if action == 'suspend' else Tenant.Status.CLOSED
        tenant.status = new_status
        tenant.status_reason = request.data.get('reason', '').strip()
        tenant.status_changed_at = timezone.now()
        tenant.save(update_fields=['status', 'status_reason', 'status_changed_at', 'updated_at'])
        AuditLog.objects.create(actor=request.user, tenant=tenant, action=new_status, reason=tenant.status_reason)
        return Response(TenantSerializer(tenant).data)

class SuperAdminMetricsView(APIView):
    permission_classes = [IsSuperAdmin]

    def get(self, request):
        from apps.billing.models import Transaction
        from apps.routers.models import NAS

        completed = Transaction.objects.filter(status='COMPLETED')
        month_start = timezone.now() - timedelta(days=30)
        all_totals = completed.aggregate(
            revenue=Sum('gross_amount'),
            platform_commission=Sum('platform_fee'),
        )
        mrr = completed.filter(created_at__gte=month_start).aggregate(total=Sum('gross_amount'))['total'] or 0
        return Response({
            'revenue': float(all_totals['revenue'] or 0),
            'mrr': float(mrr),
            'active_vendors': Tenant.objects.filter(status=Tenant.Status.ACTIVE).count(),
            'total_routers': NAS.objects.count(),
            'platform_commission': float(all_totals['platform_commission'] or 0),
        })

class VendorDashboardView(APIView):
    permission_classes = [IsVendorMember]

    def get(self, request):
        profile = getattr(request.user, 'tenant_profile', None)
        staff = getattr(request.user, 'staff_profile', None)
        tenant_id = str(profile.tenant_id if profile else staff.tenant_id)
        from apps.billing.models import Transaction
        from apps.routers.models import NAS

        recent_transactions = []
        routers = NAS.objects.none()
        if tenant_id:
            today = timezone.localdate()
            transactions = Transaction.objects.filter(tenant_id=tenant_id)
            recent_transactions = transactions.order_by('-created_at')[:10]
            routers = NAS.objects.filter(tenant_id=tenant_id)
            daily = transactions.filter(status='COMPLETED', created_at__date=today).aggregate(
                revenue=Sum('gross_amount'),
                net=Sum('vendor_net_amount'),
            )
        else:
            daily = {'revenue': 0, 'net': 0}
        data = {
            "daily_revenue": float(daily['revenue'] or 0),
            "net_earnings": float(daily['net'] or 0),
            "active_routers": routers.filter(is_online=True).count(),
            "total_routers": routers.count(),
            "recent_transactions": [
                {
                    'id': transaction.id,
                    'gross_amount': transaction.gross_amount,
                    'platform_fee': transaction.platform_fee,
                    'vendor_net_amount': transaction.vendor_net_amount,
                    'status': transaction.status,
                    'payment_method': transaction.payment_method,
                    'created_at': transaction.created_at,
                }
                for transaction in recent_transactions
            ],
        }
        return Response(data)
