from rest_framework.permissions import BasePermission

from apps.tenants.models import Tenant, TenantStaff, TenantUser


def tenant_for_user(user):
    profile = getattr(user, 'tenant_profile', None)
    if profile and profile.tenant_id:
        return profile.tenant
    staff = getattr(user, 'staff_profile', None)
    if staff and staff.is_active:
        return staff.tenant
    return None


def is_active_vendor_member(user):
    tenant = tenant_for_user(user)
    profile = getattr(user, 'tenant_profile', None)
    return bool(
        tenant
        and tenant.status == Tenant.Status.ACTIVE
        and (
            profile and profile.role == TenantUser.Role.VENDOR
            or getattr(user, 'staff_profile', None)
        )
    )


class IsSuperAdminOnly(BasePermission):
    message = 'SuperAdmin access is required.'

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_superadmin)


class IsVendorOwner(BasePermission):
    message = 'Vendor owner access is required.'

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_vendor and is_active_vendor_member(request.user))


class IsVendorMember(BasePermission):
    message = 'Active vendor account access is required.'

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and is_active_vendor_member(request.user))


class HasStaffPermission(BasePermission):
    message = 'Your staff role does not permit this action.'

    def __init__(self, *roles):
        self.roles = set(roles)

    def has_permission(self, request, view):
        if request.user and request.user.is_authenticated and request.user.is_superadmin:
            return True
        if request.user and request.user.is_authenticated and request.user.is_vendor and is_active_vendor_member(request.user):
            return True
        staff = getattr(request.user, 'staff_profile', None)
        return bool(staff and staff.is_active and staff.tenant.status == Tenant.Status.ACTIVE and staff.role in self.roles)


class IsVendorManager(HasStaffPermission):
    def __init__(self):
        super().__init__(TenantStaff.Role.MANAGER)


class IsVendorTechnician(HasStaffPermission):
    def __init__(self):
        super().__init__(TenantStaff.Role.MANAGER, TenantStaff.Role.TECHNICIAN)


class IsVendorCashier(HasStaffPermission):
    def __init__(self):
        super().__init__(TenantStaff.Role.MANAGER, TenantStaff.Role.CASHIER)


class IsVendorPlanViewer(HasStaffPermission):
    def __init__(self):
        super().__init__(TenantStaff.Role.MANAGER, TenantStaff.Role.TECHNICIAN, TenantStaff.Role.CASHIER)


class IsSuperAdminOrVendor(BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and (request.user.is_superadmin or is_active_vendor_member(request.user))
        )
