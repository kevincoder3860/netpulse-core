from django.urls import path
from .views import AnalyticsDashboardView, TelemetryHealthView

urlpatterns = [
	path('analytics/dashboard/', AnalyticsDashboardView.as_view(), name='analytics-dashboard'),
	path('telemetry/health/', TelemetryHealthView.as_view(), name='telemetry-health'),
]
