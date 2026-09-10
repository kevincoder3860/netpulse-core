from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    RegisterView, SuperAdminMetricsView, SuperAdminTenantActionView,
    TenantViewSet, VendorDashboardView, VendorStaffDetailView, VendorStaffView,
)
from .auth import CustomTokenObtainPairView
from rest_framework_simplejwt.views import TokenRefreshView

router = DefaultRouter()
router.register(r'tenants', TenantViewSet, basename='tenants')

urlpatterns = [
    path('', include(router.urls)),
    path('auth/register/vendor/', RegisterView.as_view(), name='register-vendor'),
    path('auth/login/', CustomTokenObtainPairView.as_view(), name='login'),
    path('auth/refresh/', TokenRefreshView.as_view(), name='refresh'),
    path('superadmin/metrics/', SuperAdminMetricsView.as_view(), name='superadmin-metrics'),
    path('vendors/dashboard/', VendorDashboardView.as_view(), name='vendor-dashboard'),
    path('vendors/staff/', VendorStaffView.as_view(), name='vendor-staff'),
    path('vendors/staff/<int:staff_id>/', VendorStaffDetailView.as_view(), name='vendor-staff-detail'),
    path('superadmin/tenants/<uuid:tenant_id>/<str:action>/', SuperAdminTenantActionView.as_view(), name='superadmin-tenant-action'),
]
