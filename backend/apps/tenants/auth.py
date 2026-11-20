from django.contrib.auth import get_user_model
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.views import TokenObtainPairView

from core.permissions import (
    is_active_vendor_member,
    is_superadmin_user,
    role_for_user,
    tenant_for_user,
)


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        identifier = attrs.get(self.username_field, '').strip()
        User = get_user_model()
        if '@' in identifier:
            user = User.objects.filter(email__iexact=identifier).first()
            if user:
                attrs[self.username_field] = user.get_username()

        data = super().validate(attrs)
        staff = getattr(self.user, 'staff_profile', None)
        if not self.user.is_active:
            raise AuthenticationFailed('This account is inactive.')
        if staff and not staff.is_active:
            raise AuthenticationFailed('This staff account is inactive.')
        if not role_for_user(self.user):
            raise AuthenticationFailed('This account has no valid platform role.')

        tenant = tenant_for_user(self.user)
        if tenant and tenant.status != 'ACTIVE':
            raise AuthenticationFailed(
                f'Your network account is {tenant.status.lower()}. Please contact support.'
            )

        token = self.get_token(self.user)
        data.update({
            'role': token.get('role'),
            'tenant_id': token.get('tenant_id'),
            'email': token.get('email'),
            'staff_role': token.get('staff_role'),
            'is_superadmin': token.get('is_superadmin'),
            'is_vendor': token.get('is_vendor'),
            'redirect': {
                'SUPERADMIN': '/superadmin',
                'CUSTOMER': '/customer',
            }.get(token.get('role'), '/vendor'),
        })
        return data

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        role = role_for_user(user)
        is_superadmin = is_superadmin_user(user)
        is_vendor = is_active_vendor_member(user)
        tenant = tenant_for_user(user)
        staff = getattr(user, 'staff_profile', None)

        token['role'] = role
        token['is_superadmin'] = is_superadmin
        token['is_vendor'] = is_vendor
        token['tenant_id'] = str(tenant.pk) if tenant else None
        token['staff_role'] = staff.role if staff and staff.is_active else None
        token['email'] = user.email
        return token


class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer
