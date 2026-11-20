from rest_framework.permissions import BasePermission
from django.core.exceptions import ObjectDoesNotExist

from apps.tenants.models import Tenant, TenantStaff, TenantUser


def related_profile(user, name):
    try:
        return getattr(user, name, None)
    except (AttributeError, ObjectDoesNotExist):
        return None


def is_active_authenticated_user(user):
    return bool(
        user
        and getattr(user, 'is_authenticated', False)
        and getattr(user, 'is_active', False)
    )


def is_superadmin_user(user):
    if not user:
        return False
    if bool(getattr(user, 'is_superuser', False)):
        return True
    platform_profile = related_profile(user, 'platform_profile')
    return bool(platform_profile and platform_profile.role == 'SUPERADMIN')


def tenant_for_user(user):
    if is_superadmin_user(user):
        return None

    profile = related_profile(user, 'tenant_profile')
    staff = related_profile(user, 'staff_profile')
    customer = related_profile(user, 'customer_profile')
    if related_profile(user, 'platform_profile') or (profile and staff):
        return None
    if customer:
        return customer.tenant if not profile and not staff else None
    if profile and profile.role == TenantUser.Role.VENDOR and profile.tenant_id:
        return profile.tenant
    if staff and staff.is_active:
        return staff.tenant
    return None


def is_active_vendor_member(user):
    if not is_active_authenticated_user(user) or is_superadmin_user(user):
        return False
    if related_profile(user, 'platform_profile') or related_profile(user, 'customer_profile'):
        return False

    tenant = tenant_for_user(user)
    profile = related_profile(user, 'tenant_profile')
    staff = related_profile(user, 'staff_profile')
    if profile and staff:
        return False
    owns_tenant = bool(profile and profile.role == TenantUser.Role.VENDOR)
    is_active_staff = bool(staff and staff.is_active)
    return bool(
        tenant
        and tenant.status == Tenant.Status.ACTIVE
        and (owns_tenant or is_active_staff)
    )


def role_for_user(user):
    if is_superadmin_user(user):
        return 'SUPERADMIN'

    profile = related_profile(user, 'tenant_profile')
    staff = related_profile(user, 'staff_profile')
    platform_profile = related_profile(user, 'platform_profile')
    customer = related_profile(user, 'customer_profile')
    if sum(bool(item) for item in (profile, staff, platform_profile, customer)) > 1:
        return None
    if platform_profile:
        return platform_profile.role
    if profile and profile.role == TenantUser.Role.VENDOR:
        return 'VENDOR'
    if staff and staff.is_active:
        return 'STAFF'
    return 'CUSTOMER' if customer else None


class IsSuperAdminOnly(BasePermission):
    message = 'SuperAdmin access is required.'

    def has_permission(self, request, _view):
        user = getattr(request, 'user', None)
        return bool(is_active_authenticated_user(user) and is_superadmin_user(user))


class IsCustomer(BasePermission):
    message = 'An active customer account is required.'

    def has_permission(self, request, _view):
        user = getattr(request, 'user', None)
        if not is_active_authenticated_user(user) or is_superadmin_user(user):
            return False
        if any(related_profile(user, name) for name in ('tenant_profile', 'staff_profile', 'platform_profile')):
            return False
        customer = related_profile(user, 'customer_profile')
        return bool(customer and customer.tenant.status == Tenant.Status.ACTIVE)


class IsVendor(BasePermission):
    message = 'Active vendor account access is required.'

    def has_permission(self, request, _view):
        user = getattr(request, 'user', None)
        return bool(is_active_authenticated_user(user) and is_active_vendor_member(user))


class IsVendorOwner(BasePermission):
    message = 'Vendor owner access is required.'

    def has_permission(self, request, _view):
        user = getattr(request, 'user', None)
        profile = related_profile(user, 'tenant_profile') if user else None
        return bool(
            is_active_authenticated_user(user)
            and profile
            and profile.role == TenantUser.Role.VENDOR
            and is_active_vendor_member(user)
        )


class IsVendorMember(IsVendor):
    pass


class HasStaffPermission(BasePermission):
    message = 'Your staff role does not permit this action.'

    def __init__(self, *roles):
        self.roles = set(roles)

    def has_permission(self, request, _view):
        user = getattr(request, 'user', None)
        if not is_active_authenticated_user(user):
            return False
        if is_superadmin_user(user):
            return True
        if is_active_vendor_member(user):
            profile = related_profile(user, 'tenant_profile')
            if profile and profile.role == TenantUser.Role.VENDOR:
                return True
        staff = related_profile(user, 'staff_profile')
        return bool(
            staff
            and staff.is_active
            and staff.tenant.status == Tenant.Status.ACTIVE
            and staff.role in self.roles
            and not related_profile(user, 'tenant_profile')
            and not related_profile(user, 'customer_profile')
            and not related_profile(user, 'platform_profile')
        )


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
    message = 'SuperAdmin or active vendor access is required.'

    def has_permission(self, request, _view):
        user = getattr(request, 'user', None)
        return bool(
            is_active_authenticated_user(user)
            and (is_superadmin_user(user) or is_active_vendor_member(user))
        )
