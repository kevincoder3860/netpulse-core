from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.views import TokenObtainPairView
from django.contrib.auth import get_user_model
from rest_framework.exceptions import AuthenticationFailed
from .models import TenantStaff, TenantUser


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        identifier = attrs.get(self.username_field, '').strip()
        User = get_user_model()
        if '@' in identifier:
            user = User.objects.filter(email__iexact=identifier).first()
            if user:
                attrs[self.username_field] = user.get_username()
        data = super().validate(attrs)
        profile = getattr(self.user, 'tenant_profile', None)
        staff = getattr(self.user, 'staff_profile', None)
        tenant = profile.tenant if profile else staff.tenant if staff else None
        if tenant and tenant.status != 'ACTIVE':
            raise AuthenticationFailed(f'Your vendor account is {tenant.status.lower()}. Please contact support.')
        if staff and not staff.is_active:
            raise AuthenticationFailed('This staff account is inactive.')
        token = self.get_token(self.user)
        data['role'] = token.get('role')
        data['tenant_id'] = token.get('tenant_id')
        data['email'] = token.get('email')
        data['staff_role'] = token.get('staff_role')
        data['is_superadmin'] = token.get('is_superadmin')
        data['is_vendor'] = token.get('is_vendor')
        data['redirect'] = '/admin/dashboard' if token.get('role') == 'SUPERADMIN' else '/vendor/dashboard'
        return data

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        profile = getattr(user, 'tenant_profile', None)
        staff = getattr(user, 'staff_profile', None)
        role = profile.role if profile else 'STAFF' if staff else (TenantUser.Role.SUPERADMIN if user.is_superuser else None)
        token['role'] = role
        token['is_superadmin'] = bool(role == TenantUser.Role.SUPERADMIN and user.is_superuser)
        token['is_vendor'] = role == TenantUser.Role.VENDOR
        tenant_id = profile.tenant_id if profile and profile.tenant_id else staff.tenant_id if staff else None
        token['tenant_id'] = str(tenant_id) if tenant_id else None
        token['staff_role'] = staff.role if staff else None
        token['email'] = user.email
        return token



class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer