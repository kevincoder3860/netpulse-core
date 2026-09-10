from django.apps import AppConfig

class TenantsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.tenants'

    def ready(self):
        from django.contrib.auth import get_user_model
        from .models import Tenant, TenantStaff, TenantUser

        User = get_user_model()

        if not hasattr(User, 'role'):
            User.add_to_class('role', property(lambda user: (
                user.tenant_profile.role if hasattr(user, 'tenant_profile') else
                'VENDOR_STAFF' if hasattr(user, 'staff_profile') else None
            )))
        if not hasattr(User, 'tenant'):
            User.add_to_class('tenant', property(lambda user: (
                user.tenant_profile.tenant if hasattr(user, 'tenant_profile') and user.tenant_profile.tenant_id else
                user.staff_profile.tenant if hasattr(user, 'staff_profile') and user.staff_profile.is_active else None
            )))
        if not hasattr(User, 'is_superadmin'):
            User.add_to_class('is_superadmin', property(lambda user: user.role == TenantUser.Role.SUPERADMIN and user.is_superuser))
        if not hasattr(User, 'is_vendor'):
            User.add_to_class('is_vendor', property(lambda user: user.role == TenantUser.Role.VENDOR and user.tenant is not None))
