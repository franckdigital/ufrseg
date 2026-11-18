from django.db.models import Q
from rest_framework import permissions, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsBackOffice

from . import assistant
from .models import FAQ, Annonce, ContactMessage, Evenement, Notification, Offre


class PublicRead(permissions.BasePermission):
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return bool(request.user and request.user.is_authenticated and request.user.is_back_office)


def make(model, **meta):
    return type(f"{model.__name__}Serializer", (serializers.ModelSerializer,), {"Meta": type("Meta", (), {"model": model, "fields": "__all__", **meta})})


AnnonceSerializer = make(Annonce, read_only_fields=["auteur"])
EvenementSerializer = make(Evenement)
FAQSerializer = make(FAQ)
OffreSerializer = make(Offre)
NotificationSerializer = make(Notification)


class AnnonceViewSet(viewsets.ModelViewSet):
    serializer_class = AnnonceSerializer
    permission_classes = [PublicRead]
    filterset_fields = ["categorie", "niveau", "epingle"]
    search_fields = ["titre", "resume"]

    def get_queryset(self):
        u = self.request.user
        return Annonce.objects.all() if (u.is_authenticated and u.is_back_office) else Annonce.objects.filter(publie=True)

    def perform_create(self, serializer):
        a = serializer.save(auteur=self.request.user)
        if a.publie:
            from apps.accounts.models import User

            qs = User.objects.filter(role="ETUDIANT", is_active=True)
            if a.niveau:
                qs = qs.filter(classe__niveau=a.niveau)
            Notification.objects.bulk_create([Notification(user=u, titre=a.titre, message=a.resume, lien=f"/annonces/{a.id}") for u in qs[:5000]])


class EvenementViewSet(viewsets.ModelViewSet):
    queryset = Evenement.objects.all()
    serializer_class = EvenementSerializer
    permission_classes = [PublicRead]
    filterset_fields = ["type", "niveau", "classe"]
    pagination_class = None


class FAQViewSet(viewsets.ModelViewSet):
    queryset = FAQ.objects.all()
    serializer_class = FAQSerializer
    permission_classes = [PublicRead]
    search_fields = ["question", "reponse"]
    pagination_class = None


class OffreViewSet(viewsets.ModelViewSet):
    queryset = Offre.objects.filter(actif=True)
    serializer_class = OffreSerializer
    permission_classes = [PublicRead]
    filterset_fields = ["type"]


class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = NotificationSerializer

    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user)[:100]

    @action(detail=False, methods=["post"])
    def read_all(self, request):
        Notification.objects.filter(user=request.user, lue=False).update(lue=True)
        return Response({"ok": True})

    @action(detail=False)
    def unread_count(self, request):
        return Response({"count": Notification.objects.filter(user=request.user, lue=False).count()})


class ContactView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    throttle_scope = "auth"

    def post(self, request):
        s = make(ContactMessage, read_only_fields=["traite", "created"])(data=request.data)
        s.is_valid(raise_exception=True)
        s.save()
        return Response({"ok": True}, status=201)


class AssistantView(APIView):
    """Agent IA public de la vitrine (aussi utilisé par l'application mobile)."""

    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    throttle_scope = "assistant"

    def post(self, request):
        q = (request.data.get("question") or "").strip()
        if not q:
            return Response({"detail": "Question vide."}, status=400)
        answer, engine = assistant.ask(q, request.data.get("history"))
        return Response({"answer": answer, "engine": engine})


class PublicStatsView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get(self, request):
        from apps.academics.models import Filiere
        from apps.accounts.models import User
        from apps.library.models import Document

        return Response({
            "etudiants": User.objects.filter(role="ETUDIANT").count(),
            "documents": Document.objects.filter(statut="PUBLIE").count(),
            "filieres": Filiere.objects.count(),
            "enseignants": User.objects.filter(role="ENSEIGNANT").count(),
        })
