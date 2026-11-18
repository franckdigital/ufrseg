import os

from django.core.wsgi import get_wsgi_application as get_application  # noqa

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
application = get_application()
