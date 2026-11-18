"""Accès protégé aux fichiers privés (documents payants, CV, pièces jointes, soumissions).

Aucun fichier privé n'est exposé par nginx : l'API renvoie un lien signé à durée limitée (`/api/media/?t=…`), et
cette vue streame le fichier (en production via X-Accel-Redirect, nginx ne servant que l'emplacement interne).
"""
import mimetypes

from django.conf import settings
from django.core import signing
from django.core.files.storage import default_storage
from django.db import models
from django.http import FileResponse, Http404, HttpResponse, HttpResponseForbidden
from rest_framework import permissions, serializers
from rest_framework.views import APIView

SALT = "ufrseg-media"
MAX_AGE = 3600  # 1 h


def signed_media_url(request, name):
    token = signing.dumps(name, salt=SALT)
    path = f"/api/media/?t={token}"
    return request.build_absolute_uri(path) if request else path


class SignedFileField(serializers.FileField):
    """Lecture : lien signé temporaire. Écriture : upload classique."""

    def to_representation(self, value):
        if not value:
            return None
        return signed_media_url(self.context.get("request"), value.name)


class SignedFilesMixin:
    serializer_field_mapping = {**serializers.ModelSerializer.serializer_field_mapping, models.FileField: SignedFileField}


class MediaView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get(self, request):
        try:
            name = signing.loads(request.query_params.get("t", ""), salt=SALT, max_age=MAX_AGE)
        except signing.BadSignature:
            return HttpResponseForbidden("Lien expiré ou invalide.")
        if not name or ".." in name or not default_storage.exists(name):
            raise Http404()
        ctype = mimetypes.guess_type(name)[0] or "application/octet-stream"
        if settings.USE_X_ACCEL:
            r = HttpResponse(content_type=ctype)
            r["X-Accel-Redirect"] = "/_protected/" + name
        else:
            r = FileResponse(default_storage.open(name, "rb"), content_type=ctype)
        r["Content-Disposition"] = f'inline; filename="{name.split("/")[-1]}"'
        r["Cache-Control"] = "private, max-age=300"
        return r
