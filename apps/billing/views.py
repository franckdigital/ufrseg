import hmac
import os

from django.conf import settings
from django.db import transaction
from django.db.models import Count, Sum
from django.utils import timezone
from rest_framework import permissions, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import normalize_phone
from apps.accounts.permissions import IsDeanStaff

from .models import (AuthorEarning, Payment, Payout, Plan, RemunerationRule, RevenueEntry, RevenueSplit,
                     Subscription, active_subscription)
from . import cinetpay
from .services import author_balance, confirm_payment, finalize_payment, start_payment


class PlanSerializer(serializers.ModelSerializer):
    pack_label = serializers.CharField(source="get_pack_display", read_only=True)

    class Meta:
        model = Plan
        fields = ["id", "pack", "pack_label", "mois", "prix", "actif"]


class SubscriptionSerializer(serializers.ModelSerializer):
    plan = PlanSerializer(read_only=True)
    active = serializers.BooleanField(read_only=True)

    class Meta:
        model = Subscription
        fields = ["id", "plan", "debut", "fin", "active", "annule"]


class PaymentSerializer(serializers.ModelSerializer):
    plan_label = serializers.SerializerMethodField()
    user_name = serializers.CharField(source="user.full_name", read_only=True)

    def get_plan_label(self, p):
        return str(p.plan) if p.plan_id else (p.label or p.get_purpose_display())

    class Meta:
        model = Payment
        fields = ["id", "reference", "user", "user_name", "plan", "plan_label", "purpose", "montant", "provider", "payer_phone", "status", "created", "confirmed_at"]
        read_only_fields = fields


class PlanViewSet(viewsets.ModelViewSet):
    queryset = Plan.objects.filter(actif=True)
    serializer_class = PlanSerializer
    pagination_class = None

    def get_permissions(self):
        if self.request.method in permissions.SAFE_METHODS:
            return [permissions.AllowAny()]
        return [IsDeanStaff()]


class MySubscriptionView(APIView):
    def get(self, request):
        sub = active_subscription(request.user)
        history = request.user.subscriptions.select_related("plan")
        return Response({"active": SubscriptionSerializer(sub).data if sub else None, "history": SubscriptionSerializer(history, many=True).data})


class CheckoutView(APIView):
    """Crée un paiement en attente. Le paiement réel est confirmé par le webhook de l'agrégateur."""

    def post(self, request):
        try:
            plan = Plan.objects.get(pk=request.data.get("plan"), actif=True)
        except Plan.DoesNotExist:
            return Response({"detail": "Formule introuvable."}, status=404)
        provider = request.data.get("provider")
        if provider not in Payment.Provider.values:
            return Response({"detail": "Moyen de paiement invalide."}, status=400)
        try:
            phone = normalize_phone(request.data.get("phone") or request.user.phone)
        except ValueError as e:
            return Response({"detail": str(e)}, status=400)
        p = Payment.objects.create(user=request.user, plan=plan, label=str(plan), montant=plan.prix, provider=provider, payer_phone=phone)
        try:
            data = start_payment(p)
        except cinetpay.PaymentError as e:
            return Response({"detail": str(e)}, status=502)
        return Response({**PaymentSerializer(p).data, "payment_url": data["payment_url"], "mock": data["mock"]}, status=201)


class SimulateConfirmView(APIView):
    """Confirmation manuelle — disponible uniquement en DEBUG (sandbox) pour tester sans agrégateur."""

    def post(self, request, reference):
        if not settings.DEBUG:
            return Response(status=404)
        p = Payment.objects.filter(reference=reference, user=request.user).first()
        if not p:
            return Response(status=404)
        confirm_payment(p, provider_ref="SANDBOX")
        return Response(PaymentSerializer(p).data)


class VerifyPaymentView(APIView):
    """Retour de la page de paiement / bouton « J'ai payé » : re-vérification serveur auprès de CinetPay."""

    def post(self, request, reference):
        p = Payment.objects.filter(reference=reference, user=request.user).first()
        if not p:
            return Response(status=404)
        try:
            p = finalize_payment(p)
        except cinetpay.PaymentError as e:
            return Response({"detail": str(e)}, status=502)
        return Response(PaymentSerializer(p).data)


class CinetPayWebhookView(APIView):
    """notify_url CinetPay. Le corps n'est jamais cru : le statut est re-vérifié auprès de CinetPay."""

    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get(self, request):
        return Response(status=200)  # CinetPay teste l'accessibilité de la notify_url en GET

    def post(self, request):
        ref = request.data.get("merchant_transaction_id") or request.data.get("cpm_trans_id")
        p = Payment.objects.filter(provider_ref=ref).first() if ref else None
        if not p:
            return Response(status=404)
        try:
            p = finalize_payment(p)
        except cinetpay.PaymentError:
            return Response(status=502)  # CinetPay renverra la notification
        return Response({"result": p.status})


class PaymentWebhookView(APIView):
    """Webhook agrégateur. Signé par un secret partagé (en-tête X-Webhook-Secret)."""

    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def post(self, request):
        secret = os.getenv("PAYMENT_WEBHOOK_SECRET", "")
        given = request.headers.get("X-Webhook-Secret", "")
        if not secret or not hmac.compare_digest(secret, given):
            return Response(status=403)
        p = Payment.objects.filter(reference=request.data.get("reference")).first()
        if not p:
            return Response(status=404)
        if request.data.get("status") == "SUCCESS":
            confirm_payment(p, request.data.get("provider_ref", ""))
        elif p.status == Payment.Status.PENDING:
            p.status = Payment.Status.FAILED
            p.save(update_fields=["status"])
        return Response({"ok": True})


class MyPaymentsView(APIView):
    def get(self, request):
        return Response(PaymentSerializer(request.user.payments.select_related("plan"), many=True).data)


class AuthorView(APIView):
    """Espace auteur : solde, gains, demandes de reversement."""

    def get(self, request):
        if not request.user.is_author:
            return Response({"detail": "Réservé aux auteurs contributeurs."}, status=403)
        docs = request.user.documents_ecrits.annotate(vues=Count("accesses")).values("id", "titre", "statut", "vues")
        payouts = request.user.payouts.values("id", "montant", "provider", "status", "created", "justificatif")
        return Response({"balance": author_balance(request.user), "documents": list(docs), "payouts": list(payouts)})

    @transaction.atomic
    def post(self, request):
        """Demande de reversement du solde disponible (minimum 1 000 FCFA)."""
        if not request.user.is_author:
            return Response(status=403)
        earnings = AuthorEarning.objects.select_for_update().filter(auteur=request.user, payout__isnull=True)
        total = int(earnings.aggregate(s=Sum("montant"))["s"] or 0)
        if total < 1000:
            return Response({"detail": "Solde minimum de 1 000 FCFA requis."}, status=400)
        try:
            phone = normalize_phone(request.data.get("phone") or request.user.phone)
        except ValueError as e:
            return Response({"detail": str(e)}, status=400)
        provider = request.data.get("provider", "ORANGE")
        payout = Payout.objects.create(auteur=request.user, montant=total, provider=provider, phone=phone)
        earnings.update(payout=payout)
        return Response({"id": payout.id, "montant": total}, status=201)


class FinanceViewSet(viewsets.ViewSet):
    """Pilotage financier du décanat."""

    permission_classes = [IsDeanStaff]

    @action(detail=False)
    def summary(self, request):
        ok = Payment.objects.filter(status=Payment.Status.SUCCESS)
        ventil = RevenueEntry.objects.aggregate(d=Sum("part_decanat"), a=Sum("part_auteurs"), p=Sum("part_plateforme"))
        par_pack = ok.values("purpose", "plan__pack").annotate(total=Sum("montant"), n=Count("id"))
        return Response({
            "chiffre_affaires": ok.aggregate(s=Sum("montant"))["s"] or 0,
            "abonnements_actifs": Subscription.objects.filter(annule=False, fin__gt=timezone.now()).count(),
            "paiements_en_attente": Payment.objects.filter(status=Payment.Status.PENDING).count(),
            "part_decanat": ventil["d"] or 0, "part_auteurs": ventil["a"] or 0, "part_plateforme": ventil["p"] or 0,
            "par_pack": list(par_pack),
            "reversements_en_attente": Payout.objects.filter(status=Payout.Status.REQUESTED).count(),
            "split": {"decanat": RevenueSplit.current().decanat, "auteurs": RevenueSplit.current().auteurs, "plateforme": RevenueSplit.current().plateforme},
        })

    @action(detail=False)
    def payments(self, request):
        return Response(PaymentSerializer(Payment.objects.select_related("user", "plan")[:200], many=True).data)

    @action(detail=False, methods=["get", "post"])
    def split(self, request):
        if request.method == "POST":
            try:
                s = RevenueSplit(decanat=int(request.data["decanat"]), auteurs=int(request.data["auteurs"]), plateforme=int(request.data["plateforme"]))
                s.save()
            except Exception as e:
                return Response({"detail": getattr(e, "messages", [str(e)])[0]}, status=400)
        c = RevenueSplit.current()
        return Response({"decanat": c.decanat, "auteurs": c.auteurs, "plateforme": c.plateforme})

    @action(detail=False)
    def payouts(self, request):
        rows = Payout.objects.select_related("auteur").values("id", "montant", "provider", "phone", "status", "created", "auteur__first_name", "auteur__last_name")
        return Response(list(rows))

    @action(detail=True, methods=["post"], url_path="pay-payout")
    def pay_payout(self, request, pk=None):
        p = Payout.objects.get(pk=pk)
        p.status = Payout.Status.PAID
        p.paid_at = timezone.now()
        p.justificatif = request.data.get("justificatif", "")
        p.save()
        return Response({"ok": True})
