from django.urls import path

from . import consumers

websocket_urlpatterns = [
    path(
        'ws/telemetry/<str:tenant_id>/',
        consumers.TelemetryConsumer.as_asgi(),
    ),
]
