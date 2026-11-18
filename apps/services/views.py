from django.db.models import Count, Q, Sum
from django.utils import timezone
from rest_framework import permissions, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.accounts.permissions import IsBackOffice

from apps.accounts.files import SignedFilesMixin
from .models import Demande, FraisService, RendezVous


class DemandeSerializer(SignedFilesMixin, serializers.ModelSerializer):
    type_label = serializers.CharField(source="get_type_display", read_only=True)
    statut_label = serializers.CharField(source="get_statut_display", read_only=True)
    demandeur_nom = serializers.CharField(source="demandeur.full_name", read_only=True)
    service = serializers.CharField(read_only=True)

    class Meta:
        model = Demande
        fields = ["id", "reference", "demandeur", "demandeur_nom", "type", "type_label", "objet", "details", "piece_jointe", "annee_academique", "montant",
                  "statut", "statut_label", "observations", "service", "created", "cloturee_le"]
        read_only_fields = ["reference", "demandeur", "statut", "observations", "cloturee_le", "montant"]


class DemandeViewSet(viewsets.ModelViewSet):
    serializer_class = DemandeSerializer
    filterset_fields = ["type", "statut"]
    search_fields = ["reference", "objet", "demandeur__last_name", "demandeur__first_name"]
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        u = self.request.user
        qs = Demande.objects.select_related("demandeur")
        return qs if u.is_back_office else qs.filter(demandeur=u)

    def perform_create(self, serializer):
        fee = FraisService.objects.filter(type=serializer.validated_data["type"]).first()
        if fee and fee.montant > 0:
            serializer.save(demandeur=self.request.user, montant=fee.montant, statut=Demande.Statut.PAIEMENT)
        else:
            serializer.save(demandeur=self.request.user)

    @action(detail=True, methods=["post"])
    def payer(self, request, pk=None):
        """Paiement Mobile Money des frais de traitement (relevé, bulletin, attestation d'admission)."""
        from apps.billing.models import Payment
        from apps.billing import cinetpay
        from apps.billing.services import create_fee_payment, start_payment

        d = self.get_object()
        if d.demandeur_id != request.user.id or d.statut != Demande.Statut.PAIEMENT or not d.montant:
            return Response({"detail": "Aucun paiement attendu pour ce dossier."}, status=400)
        if d.paiement_id and d.paiement.status == Payment.Status.PENDING:
            d.paiement.status = Payment.Status.FAILED  # on relance un nouveau paiement
            d.paiement.save(update_fields=["status"])
        try:
            p = create_fee_payment(request.user, d.montant, request.data.get("provider"), request.data.get("phone"), "DEMANDE", f"{d.get_type_display()} · {d.reference}")
        except ValueError as e:
            return Response({"detail": str(e)}, status=400)
        d.paiement = p
        d.save(update_fields=["paiement"])
        try:
            return Response(start_payment(p), status=201)
        except cinetpay.PaymentError as e:
            return Response({"detail": str(e)}, status=502)

    @action(detail=True, methods=["post"], permission_classes=[IsBackOffice])
    def traiter(self, request, pk=None):
        """Change le statut. Les documents officiels ne partent qu'après validation (APPROUVEE)."""
        d = self.get_object()
        statut = request.data.get("statut")
        if statut not in Demande.Statut.values:
            return Response({"detail": "Statut invalide."}, status=400)
        d.statut, d.observations, d.traite_par = statut, request.data.get("observations", d.observations), request.user
        if statut in ("CLOTUREE", "REJETEE"):
            d.cloturee_le = timezone.now()
        d.save()
        return Response(DemandeSerializer(d).data)

    @action(detail=False, url_path="suivi/(?P<ref>[A-Za-z0-9-]+)", permission_classes=[permissions.IsAuthenticated])
    def suivi(self, request, ref=None):
        d = self.get_queryset().filter(reference=ref.upper()).first()
        return Response(DemandeSerializer(d).data) if d else Response(status=404)


class FraisViewSet(viewsets.ModelViewSet):
    queryset = FraisService.objects.all()
    pagination_class = None

    def get_serializer_class(self):
        class S(serializers.ModelSerializer):
            type_label = serializers.CharField(source="get_type_display", read_only=True)

            class Meta:
                model = FraisService
                fields = ["id", "type", "type_label", "montant"]
        return S

    def get_permissions(self):
        return [permissions.IsAuthenticated()] if self.request.method in permissions.SAFE_METHODS else [IsBackOffice()]


class RdvSerializer(serializers.ModelSerializer):
    etudiant_nom = serializers.CharField(source="etudiant.full_name", read_only=True)
    avec_label = serializers.CharField(source="get_avec_display", read_only=True)

    class Meta:
        model = RendezVous
        fields = "__all__"
        read_only_fields = ["etudiant", "statut", "date_confirmee"]


class RdvViewSet(viewsets.ModelViewSet):
    serializer_class = RdvSerializer

    def get_queryset(self):
        u = self.request.user
        return RendezVous.objects.all() if u.is_back_office else RendezVous.objects.filter(etudiant=u)

    def perform_create(self, serializer):
        serializer.save(etudiant=self.request.user)

    @action(detail=True, methods=["post"], permission_classes=[IsBackOffice])
    def confirmer(self, request, pk=None):
        r = self.get_object()
        r.statut, r.date_confirmee = "CONFIRME", request.data.get("date") or r.date_souhaitee
        r.save()
        return Response(RdvSerializer(r).data)


class DashboardView(APIView):
    """Indicateurs de pilotage du décanat."""

    permission_classes = [IsBackOffice]

    def get(self, request):
        from apps.academics.models import ECUE, UE, Classe
        from apps.billing.models import Payment, Subscription
        from apps.learning.models import Copie, Devoir, Evaluation
        from apps.library.models import Document

        etu = User.objects.filter(role="ETUDIANT")
        ok = Payment.objects.filter(status="SUCCESS")
        by_month = {}
        for p in ok.values("confirmed_at", "montant"):
            k = p["confirmed_at"].strftime("%Y-%m")
            by_month[k] = by_month.get(k, 0) + p["montant"]
        return Response({
            "etudiants": {
                "total": etu.count(), "actifs": etu.filter(is_active=True).count(),
                "par_niveau": list(etu.exclude(classe=None).values("classe__niveau").annotate(n=Count("id")).order_by("classe__niveau")),
                "demandes_en_attente": Demande.objects.filter(statut__in=["SOUMISE", "VERIF", "TRAITEMENT"]).count(),
            },
            "pedagogie": {
                "ues": UE.objects.count(), "ecues": ECUE.objects.count(), "classes": Classe.objects.count(),
                "devoirs": Devoir.objects.count(), "evaluations": Evaluation.objects.count(), "copies": Copie.objects.count(),
            },
            "bibliotheque": {
                "total": Document.objects.count(), "en_attente": Document.objects.filter(statut__in=["SOUMIS", "REVISION"]).count(),
                "par_categorie": list(Document.objects.filter(statut="PUBLIE").values("categorie").annotate(n=Count("id"))),
            },
            "finance": {
                "chiffre_affaires": ok.aggregate(s=Sum("montant"))["s"] or 0,
                "abonnements_actifs": Subscription.objects.filter(annule=False, fin__gt=timezone.now()).count(),
                "par_mois": [{"mois": k, "montant": v} for k, v in sorted(by_month.items())],
            },
            "demandes_par_type": list(Demande.objects.values("type").annotate(n=Count("id")).order_by("-n")),
        })
