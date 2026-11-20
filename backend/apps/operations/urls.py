from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    ActiveSessionDisconnectView, ActiveSessionListView, CustomerPasswordView,
    CustomerProfileView, CustomerViewSet, InvoiceViewSet, PlatformSettingsView,
    SessionHistoryView, SupportTicketViewSet, SystemUserViewSet,
)

router = DefaultRouter()
router.register('customers', CustomerViewSet, basename='customers')
router.register('invoices', InvoiceViewSet, basename='invoices')
router.register('tickets', SupportTicketViewSet, basename='tickets')
router.register('superadmin/users', SystemUserViewSet, basename='system-users')

urlpatterns = [
    path('', include(router.urls)),
    path('superadmin/settings/', PlatformSettingsView.as_view(), name='platform-settings'),
    path('sessions/active/', ActiveSessionListView.as_view(), name='active-sessions'),
    path('sessions/history/', SessionHistoryView.as_view(), name='session-history'),
    path('sessions/<int:session_id>/disconnect/', ActiveSessionDisconnectView.as_view(), name='disconnect-session'),
    path('customer/profile/', CustomerProfileView.as_view(), name='customer-profile'),
    path('customer/password/', CustomerPasswordView.as_view(), name='customer-password'),
]
