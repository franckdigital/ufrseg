import os

from django.core.asgi import get_asgi_application as get_application  # noqa

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
application = get_application()
