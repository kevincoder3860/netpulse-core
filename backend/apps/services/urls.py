from django.urls import include, path
from rest_framework.routers import DefaultRouter
from .views import BurstProfileViewSet, FUPProfileViewSet

router = DefaultRouter()
router.register('burst-profiles', BurstProfileViewSet, basename='burst-profiles')
router.register('fup-profiles', FUPProfileViewSet, basename='fup-profiles')
urlpatterns = [path('', include(router.urls))]
