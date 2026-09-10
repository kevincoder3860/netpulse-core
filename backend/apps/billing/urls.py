from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    BlockedSTKNumberViewSet, CommissionRecordViewSet, InitiatePaymentView,
    MpesaCallbackView, SalesAgentViewSet, TransactionStatusView,
    CreateHotspotPlanView, HotspotPlanViewSet, TransactionViewSet,
)

router = DefaultRouter()
router.register(r'plans', HotspotPlanViewSet, basename='plans')
router.register(r'transactions', TransactionViewSet, basename='transactions')
router.register(r'blocked-stk-numbers', BlockedSTKNumberViewSet, basename='blocked-stk-numbers')
router.register(r'sales-agents', SalesAgentViewSet, basename='sales-agents')
router.register(r'commissions', CommissionRecordViewSet, basename='commissions')

urlpatterns = [
    path('', include(router.urls)),
    path('packages/create/', CreateHotspotPlanView.as_view(), name='create-hotspot-plan'),
    path('payments/initiate/', InitiatePaymentView.as_view(), name='initiate-payment'),
    path('billing/mpesa/stk-push/', InitiatePaymentView.as_view(), name='mpesa-stk-push'),
    path('mpesa/callback/', MpesaCallbackView.as_view(), name='mpesa-callback'),
    path('transactions/<str:checkout_request_id>/status/', TransactionStatusView.as_view(), name='transaction-status'),
]
