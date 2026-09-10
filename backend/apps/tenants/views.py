from rest_framework import viewsets
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.permissions import AllowAny
from rest_framework import status
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework_simplejwt.tokens import AccessToken
from .models import AuditLog, Tenant, TenantStaff, TenantUser
from .serializers import StaffInviteSerializer, StaffSerializer, TenantSerializer, RegisterSerializer
from .permissions import IsSuperAdmin, IsVendorManager, IsVendorMember, IsVendorOwner


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
        profile = getattr(self.request.user, 'tenant_profile', None)
        if profile and profile.role == TenantUser.Role.VENDOR:
            return [IsVendorOwner()]
        return [IsSuperAdmin()] if self.request.method != 'GET' or not getattr(self.request.user, 'staff_profile', None) else [IsVendorMember()]

    def get_queryset(self):
        profile = getattr(self.request.user, 'tenant_profile', None)
        if profile and profile.role == 'VENDOR':
            return self.queryset.filter(id=profile.tenant_id)
        staff = getattr(self.request.user, 'staff_profile', None)
        if staff:
            return self.queryset.filter(id=staff.tenant_id)
        return self.queryset


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
        # Placeholder for metrics
        data = {
            "revenue": 50000,
            "mrr": 5000,
            "active_vendors": 12,
            "total_routers": 45,
            "platform_commission": 5000
        }
        return Response(data)

class VendorDashboardView(APIView):
    permission_classes = [IsVendorMember]

    def get(self, request):
        profile = getattr(request.user, 'tenant_profile', None)
        staff = getattr(request.user, 'staff_profile', None)
        tenant_id = str(profile.tenant_id if profile else staff.tenant_id)
        transactions = []
        routers = []
        if tenant_id:
            from apps.billing.models import Transaction
            from apps.routers.models import NAS
            transactions = Transaction.objects.filter(tenant_id=tenant_id).order_by('-created_at')[:100]
            routers = NAS.objects.filter(tenant_id=tenant_id)
        total = sum((transaction.gross_amount for transaction in transactions), 0)
        net = sum((transaction.vendor_net_amount for transaction in transactions), 0)
        data = {
            "daily_revenue": total,
            "net_earnings": net,
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
                for transaction in transactions
            ],
        }
        return Response(data)
