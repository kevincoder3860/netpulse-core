import os

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator
from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')

django_asgi_app = get_asgi_application()

from apps.telemetry.routing import websocket_urlpatterns  # noqa: E402
from django.conf import settings  # noqa: E402

_ws_stack = AuthMiddlewareStack(URLRouter(websocket_urlpatterns))

# AllowedHostsOriginValidator only validates against ALLOWED_HOSTS.
# In local dev ALLOWED_HOSTS = ['*'] is too broad — the validator rejects
# browser origins like localhost:5173 causing instant CONNECT→DISCONNECT.
# In production (DEBUG=False) we wrap with the validator for security.
if settings.DEBUG:
    _ws_app = _ws_stack
else:
    _ws_app = AllowedHostsOriginValidator(_ws_stack)

application = ProtocolTypeRouter({
    'http': django_asgi_app,
    'websocket': _ws_app,
})

