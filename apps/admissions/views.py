from rest_framework import permissions, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.permissions import IsBackOffice
from apps.billing.models import Payment
from apps.billing import cinetpay
from apps.billing.services import create_fee_payment, start_payment
from apps.communication.models import Notification

from apps.accounts.files import SignedFilesMixin
from .models import Candidature, Guide, Programme


class PublicReadStaffWrite(permissions.BasePermission):
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        u = request.user
        return bool(u and u.is_authenticated and u.is_back_office)


class GuideViewSet(viewsets.ModelViewSet):
    permission_classes = [PublicReadStaffWrite]
    pagination_class = None
    filterset_fields = ["categorie"]

    def get_queryset(self):
        u = self.request.user
        qs = Guide.objects.all()
        return qs if (u.is_authenticated and u.is_back_office) else qs.filter(publie=True)

    def get_serializer_class(self):
        class S(serializers.ModelSerializer):
            class Meta:
                model = Guide
                fields = "__all__"
        return S


class ProgrammeSerializer(serializers.ModelSerializer):
    niveau_label = serializers.CharField(source="get_niveau_display", read_only=True)
    type_label = serializers.CharField(source="get_type_display", read_only=True)
    filiere_nom = serializers.CharField(source="filiere.nom", read_only=True, default=None)
    nb_candidatures = serializers.IntegerField(source="candidatures.count", read_only=True)
    criteres_liste = serializers.SerializerMethodField()
    pieces_liste = serializers.SerializerMethodField()

    class Meta:
        model = Programme
        fields = "__all__"

    def get_criteres_liste(self, p):
        return [l.strip() for l in p.criteres.splitlines() if l.strip()]

    def get_pieces_liste(self, p):
        return [l.strip() for l in p.pieces.splitlines() if l.strip()]


class ProgrammeViewSet(viewsets.ModelViewSet):
    serializer_class = ProgrammeSerializer
    permission_classes = [PublicReadStaffWrite]
    pagination_class = None
    filterset_fields = ["niveau", "type", "ouvert"]

    def get_queryset(self):
        return Programme.objects.select_related("filiere")


class CandidatureSerializer(SignedFilesMixin, serializers.ModelSerializer):
    programme_nom = serializers.CharField(source="programme.nom", read_only=True)
    programme_niveau = serializers.CharField(source="programme.niveau", read_only=True)
    candidat_nom = serializers.CharField(source="candidat.full_name", read_only=True)
    candidat_phone = serializers.CharField(source="candidat.phone", read_only=True)
    statut_label = serializers.CharField(source="get_statut_display", read_only=True)
    moyenne_generale = serializers.FloatField(read_only=True)

    class Meta:
        model = Candidature
        fields = "__all__"
        read_only_fields = ["reference", "candidat", "statut", "montant", "paiement", "observations", "decide_par", "annee"]

    def validate(self, a):
        p = a.get("programme")
        if p and not p.ouvert:
            raise serializers.ValidationError("Les candidatures sont closes pour ce programme.")
        req = self.context.get("request")
        if p and req and Candidature.objects.filter(candidat=req.user, programme=p, annee=Candidature._meta.get_field("annee").default).exists():
            raise serializers.ValidationError("Vous avez déjà une candidature pour ce programme cette année.")
        for k in ("moyenne_l1", "moyenne_l2", "moyenne_l3"):
            v = a.get(k)
            if v is not None and not 0 <= v <= 20:
                raise serializers.ValidationError({k: "La moyenne doit être comprise entre 0 et 20."})
        if p and p.niveau == "DOC" and not a.get("sujet_recherche"):
            raise serializers.ValidationError({"sujet_recherche": "Décrivez votre projet de recherche."})
        return a


class CandidatureViewSet(viewsets.ModelViewSet):
    serializer_class = CandidatureSerializer
    filterset_fields = ["programme", "statut", "programme__niveau"]
    search_fields = ["reference", "candidat__last_name", "candidat__first_name"]
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        u = self.request.user
        qs = Candidature.objects.select_related("programme", "candidat")
        return qs if u.is_back_office else qs.filter(candidat=u)

    def perform_create(self, serializer):
        p = serializer.validated_data["programme"]
        # Une candidature par programme et par année ; en cas de brouillon existant, on le met à jour.
        serializer.save(candidat=self.request.user, montant=p.frais_dossier)

    @action(detail=True, methods=["post"])
    def payer(self, request, pk=None):
        """Paiement Mobile Money des frais de traitement : la candidature est soumise à la confirmation du paiement."""
        c = self.get_object()
        if c.candidat_id != request.user.id or c.statut != Candidature.Statut.BROUILLON:
            return Response({"detail": "Cette candidature n'attend pas de paiement."}, status=400)
        if c.paiement_id and c.paiement.status == Payment.Status.PENDING:
            c.paiement.status = Payment.Status.FAILED
            c.paiement.save(update_fields=["status"])
        try:
            p = create_fee_payment(request.user, c.montant, request.data.get("provider"), request.data.get("phone"), "CANDIDATURE", f"Frais de dossier {c.programme.nom} · {c.reference}")
        except ValueError as e:
            return Response({"detail": str(e)}, status=400)
        c.paiement = p
        c.save(update_fields=["paiement"])
        try:
            return Response(start_payment(p), status=201)
        except cinetpay.PaymentError as e:
            return Response({"detail": str(e)}, status=502)

    @action(detail=True, methods=["post"], permission_classes=[IsBackOffice])
    def decider(self, request, pk=None):
        c = self.get_object()
        st = request.data.get("statut")
        if st not in Candidature.Statut.values or st == Candidature.Statut.BROUILLON:
            return Response({"detail": "Statut invalide."}, status=400)
        if c.statut == Candidature.Statut.BROUILLON:
            return Response({"detail": "Frais de dossier non réglés : candidature non recevable."}, status=400)
        c.statut, c.observations, c.decide_par = st, request.data.get("observations", c.observations), request.user
        c.save()
        Notification.objects.create(user=c.candidat, titre=f"Candidature {c.programme.nom} : {c.get_statut_display()}", message=c.observations[:300], lien="/master")
        return Response(CandidatureSerializer(c).data)

    @action(detail=False, permission_classes=[IsBackOffice])
    def stats(self, request):
        from django.db.models import Count
        return Response({"par_statut": list(Candidature.objects.values("statut").annotate(n=Count("id"))),
                         "par_programme": list(Candidature.objects.exclude(statut="BROUILLON").values("programme__nom").annotate(n=Count("id")))})
