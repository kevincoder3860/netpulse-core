from django.contrib import admin
from django.urls import path, include
from rest_framework_simplejwt.views import TokenRefreshView
from apps.tenants.auth import CustomTokenObtainPairView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/token/', CustomTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('api/v1/', include('apps.tenants.urls')),
    path('api/v1/', include('apps.routers.urls')),
    path('api/v1/', include('apps.billing.urls')),
    path('api/v1/', include('apps.analytics.urls')),
    path('api/v1/', include('apps.vouchers.urls')),
    path('api/v1/', include('apps.services.urls')),
]
