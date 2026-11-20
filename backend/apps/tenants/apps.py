from django.apps import AppConfig


class TenantsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.tenants'

    def ready(self):
        from django.contrib.auth import get_user_model
        from core.permissions import (
            is_active_vendor_member,
            is_superadmin_user,
            role_for_user,
            tenant_for_user,
        )

        User = get_user_model()
        if not hasattr(User, 'role'):
            User.add_to_class('role', property(role_for_user))
        if not hasattr(User, 'tenant'):
            User.add_to_class('tenant', property(tenant_for_user))
        if not hasattr(User, 'is_superadmin'):
            User.add_to_class('is_superadmin', property(is_superadmin_user))
        if not hasattr(User, 'is_vendor'):
            User.add_to_class('is_vendor', property(is_active_vendor_member))

        from . import signals
