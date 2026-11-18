from django.db.models import Avg, Count, Q
from django.http import FileResponse
from django.utils import timezone
from rest_framework import permissions, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.permissions import IsBackOffice
from apps.billing.models import Plan, active_subscription
from apps.accounts.files import signed_media_url
from apps.billing.services import record_access

from .models import Document, DocumentAccess, Favorite, Review


def user_can_access(user, doc: Document) -> bool:
    """Règle d'accès : staff/auteur = oui ; Essentiel = hors corrections ; Premium = tout."""
    if user.is_back_office or doc.auteur_id == user.id or user.role == "ENSEIGNANT":
        return True
    sub = active_subscription(user)
    if not sub:
        return False
    if doc.is_premium:
        return sub.plan.pack == Plan.Pack.PREMIUM
    return True


class DocumentSerializer(serializers.ModelSerializer):
    auteur_nom = serializers.CharField(source="auteur.full_name", read_only=True, default=None)
    filiere_nom = serializers.CharField(source="filiere.nom", read_only=True, default=None)
    ue_code = serializers.CharField(source="ue.code", read_only=True, default=None)
    ecue_code = serializers.CharField(source="ecue.code", read_only=True, default=None)
    annee_libelle = serializers.CharField(source="annee.libelle", read_only=True, default=None)
    is_premium = serializers.BooleanField(read_only=True)
    a_correction = serializers.BooleanField(read_only=True)
    accessible = serializers.SerializerMethodField()
    favori = serializers.SerializerMethodField()
    note_moyenne = serializers.FloatField(read_only=True, default=None)
    nb_acces = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Document
        fields = [
            "id", "titre", "description", "categorie", "fichier", "taille", "filiere", "filiere_nom", "niveau", "annee",
            "annee_libelle", "semestre", "ue", "ue_code", "ecue", "ecue_code", "auteur", "auteur_nom", "document_lie",
            "statut", "motif_rejet", "apercu_gratuit", "created", "published_at", "is_premium", "a_correction",
            "accessible", "favori", "note_moyenne", "nb_acces",
        ]
        read_only_fields = ["auteur", "statut", "motif_rejet", "created", "published_at", "taille"]
        extra_kwargs = {"fichier": {"write_only": True}}

    def get_accessible(self, doc):
        u = self.context["request"].user
        return bool(u.is_authenticated and user_can_access(u, doc))

    def get_favori(self, doc):
        u = self.context["request"].user
        return bool(u.is_authenticated and doc.favoris.filter(user=u).exists())


class DocumentViewSet(viewsets.ModelViewSet):
    serializer_class = DocumentSerializer
    filterset_fields = ["categorie", "filiere", "niveau", "annee", "semestre", "ue", "ecue", "auteur", "statut", "document_lie"]
    search_fields = ["titre", "description", "ue__code", "ue__intitule", "ecue__intitule", "auteur__last_name"]
    ordering_fields = ["created", "titre", "nb_acces", "note_moyenne"]

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [permissions.AllowAny()]
        if self.action in ("validate", "reject", "suspend", "destroy", "update", "partial_update"):
            return [IsBackOffice()] if self.action != "destroy" else [IsBackOffice()]
        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        qs = Document.objects.select_related("auteur", "filiere", "ue", "ecue", "annee").annotate(
            note_moyenne=Avg("avis__note"), nb_acces=Count("accesses", distinct=True))
        u = self.request.user
        if self.request.query_params.get("mine") == "1" and u.is_authenticated:
            return qs.filter(auteur=u)
        if u.is_authenticated and u.is_back_office:
            return qs
        return qs.filter(statut=Document.Statut.PUBLIE)

    def perform_create(self, serializer):
        u = self.request.user
        if not (u.is_author or u.is_back_office or u.role == "ENSEIGNANT"):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Activez votre profil auteur contributeur pour soumettre un document.")
        f = self.request.FILES.get("fichier")
        extra = {"statut": Document.Statut.PUBLIE, "published_at": timezone.now()} if u.is_back_office else {}
        serializer.save(auteur=u, taille=f.size if f else 0, **extra)

    @action(detail=True, methods=["post"])
    def validate(self, request, pk=None):
        d = self.get_object()
        d.statut, d.published_at, d.motif_rejet = Document.Statut.PUBLIE, timezone.now(), ""
        d.save()
        return Response({"statut": d.statut})

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        d = self.get_object()
        d.statut, d.motif_rejet = Document.Statut.REJETE, request.data.get("motif", "")
        d.save()
        return Response({"statut": d.statut})

    @action(detail=True, methods=["post"])
    def suspend(self, request, pk=None):
        d = self.get_object()
        d.statut = Document.Statut.SUSPENDU
        d.save()
        return Response({"statut": d.statut})

    def _guard(self, request, doc):
        if not user_can_access(request.user, doc):
            msg = "Ce document nécessite le Pack Premium." if (doc.is_premium and active_subscription(request.user)) else "Abonnement requis pour accéder à ce document."
            return Response({"detail": msg, "code": "subscription_required"}, status=402)

    @action(detail=True, methods=["post"], permission_classes=[permissions.IsAuthenticated])
    def view(self, request, pk=None):
        doc = self.get_object()
        if (r := self._guard(request, doc)):
            return r
        DocumentAccess.objects.create(document=doc, user=request.user, kind="VIEW")
        record_access(request.user, doc, "VIEW")
        return Response({"url": signed_media_url(request, doc.fichier.name)})

    @action(detail=True, methods=["get"], permission_classes=[permissions.IsAuthenticated])
    def download(self, request, pk=None):
        doc = self.get_object()
        if (r := self._guard(request, doc)):
            return r
        DocumentAccess.objects.create(document=doc, user=request.user, kind="DOWNLOAD")
        record_access(request.user, doc, "DOWNLOAD")
        return FileResponse(doc.fichier.open("rb"), as_attachment=True, filename=doc.fichier.name.split("/")[-1])

    @action(detail=True, methods=["post"], permission_classes=[permissions.IsAuthenticated])
    def favorite(self, request, pk=None):
        doc = self.get_object()
        fav, created = Favorite.objects.get_or_create(user=request.user, document=doc)
        if not created:
            fav.delete()
        return Response({"favori": created})

    @action(detail=True, methods=["post"], permission_classes=[permissions.IsAuthenticated])
    def review(self, request, pk=None):
        doc = self.get_object()
        note = int(request.data.get("note", 0))
        if not 1 <= note <= 5 and not request.data.get("signalement"):
            return Response({"detail": "Note de 1 à 5."}, status=400)
        Review.objects.update_or_create(user=request.user, document=doc, defaults={
            "note": note or 1, "commentaire": request.data.get("commentaire", "")[:300], "signalement": bool(request.data.get("signalement"))})
        return Response({"ok": True})

    @action(detail=False, permission_classes=[permissions.IsAuthenticated])
    def favorites(self, request):
        qs = self.get_queryset().filter(favoris__user=request.user)
        return Response(DocumentSerializer(qs, many=True, context={"request": request}).data)

    @action(detail=False, permission_classes=[permissions.IsAuthenticated])
    def history(self, request):
        ids = DocumentAccess.objects.filter(user=request.user).values_list("document_id", flat=True)[:50]
        qs = self.get_queryset().filter(id__in=list(ids))
        return Response(DocumentSerializer(qs, many=True, context={"request": request}).data)

    @action(detail=False, permission_classes=[IsBackOffice])
    def stats(self, request):
        return Response({
            "total": Document.objects.count(),
            "publies": Document.objects.filter(statut="PUBLIE").count(),
            "en_attente": Document.objects.filter(statut__in=["SOUMIS", "REVISION"]).count(),
            "par_categorie": list(Document.objects.values("categorie").annotate(n=Count("id"))),
            "top": list(Document.objects.annotate(n=Count("accesses")).order_by("-n").values("id", "titre", "n")[:5]),
        })
