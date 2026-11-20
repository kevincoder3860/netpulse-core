from django.urls import path
from .views import TelemetryView, telemetry_view

urlpatterns = [
    path('telemetry/', TelemetryView.as_view(), name='telemetry-root'),
    path('telemetry/<str:pk>/', TelemetryView.as_view(), name='telemetry-detail'),
]
