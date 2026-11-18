from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from apps.accounts.files import MediaView
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/", include("apps.accounts.urls")),
    path("api/media/", MediaView.as_view()),
    path("api/", include("apps.academics.urls")),
    path("api/", include("apps.library.urls")),
    path("api/", include("apps.billing.urls")),
    path("api/", include("apps.learning.urls")),
    path("api/", include("apps.services.urls")),
    path("api/", include("apps.communication.urls")),
    path("api/", include("apps.admissions.urls")),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
