from django.urls import include, path
from rest_framework.routers import DefaultRouter
from .views import RechargeViewSet, VoucherViewSet

router = DefaultRouter()
router.register('vouchers', VoucherViewSet, basename='vouchers')
router.register('recharges', RechargeViewSet, basename='recharges')
urlpatterns = [path('', include(router.urls))]
