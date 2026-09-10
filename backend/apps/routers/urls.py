from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import RouterViewSet, PortalConfigView

router = DefaultRouter()
router.register(r'routers', RouterViewSet, basename='routers')
router.register(r'portal', PortalConfigView, basename='portal')

urlpatterns = [
    path('', include(router.urls)),
]
