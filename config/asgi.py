import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django_asgi = get_asgi_application()

from dash.routing import websocket_urlpatterns

application = ProtocolTypeRouter({"http": django_asgi, "websocket": URLRouter(websocket_urlpatterns)})
