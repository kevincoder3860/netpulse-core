from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    BlockedSTKNumberViewSet, CommissionRecordViewSet, InitiatePaymentView,
    MpesaCallbackView, SalesAgentViewSet, TransactionStatusView,
    CreateHotspotPlanView, HotspotPlanViewSet, TransactionViewSet,
    MpesaGatewayConfigurationView,
    PaystackStkPushView, PaystackWebhookView,
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
    path('billing/mpesa/configuration/', MpesaGatewayConfigurationView.as_view(), name='mpesa-configuration'),
    path('mpesa/callback/', MpesaCallbackView.as_view(), name='mpesa-callback'),
    path('billing/paystack/stk-push/', PaystackStkPushView.as_view(), name='paystack-stk-push'),
    path('billing/paystack/webhook/', PaystackWebhookView.as_view(), name='paystack-webhook'),
    path('transactions/<str:checkout_request_id>/status/', TransactionStatusView.as_view(), name='transaction-status'),
]
