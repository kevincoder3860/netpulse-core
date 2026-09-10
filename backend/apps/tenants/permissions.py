from core.permissions import (
    HasStaffPermission, IsVendorCashier, IsVendorManager, IsVendorMember,
    IsVendorOwner, IsVendorPlanViewer, IsVendorTechnician, IsSuperAdminOnly,
    IsSuperAdminOrVendor,
    tenant_for_user,
)
from .models import Tenant, TenantUser


IsSuperAdmin = IsSuperAdminOnly


