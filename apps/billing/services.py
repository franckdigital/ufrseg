from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from .models import (AuthorEarning, Payment, RemunerationRule, RevenueEntry, RevenueSplit, Subscription,
                     active_subscription, compute_end)


@transaction.atomic
def confirm_payment(payment: Payment, provider_ref: str = "") -> Payment:
    """Idempotent : active l'abonnement et ventile les recettes une seule fois."""
    payment = Payment.objects.select_for_update().get(pk=payment.pk)
    if payment.status == Payment.Status.SUCCESS:
        return payment
    payment.status = Payment.Status.SUCCESS
    payment.confirmed_at = timezone.now()
    payment.provider_ref = provider_ref or payment.provider_ref
    payment.save()

    if payment.plan_id:
        current = active_subscription(payment.user)
        start = current.fin if current and current.plan.pack == payment.plan.pack else timezone.now()  # renouvellement
        Subscription.objects.create(user=payment.user, plan=payment.plan, debut=start, fin=compute_end(start, payment.plan.mois))
        split = RevenueSplit.current()
        dec = payment.montant * split.decanat // 100
        aut = payment.montant * split.auteurs // 100
        RevenueEntry.objects.create(payment=payment, part_decanat=dec, part_auteurs=aut, part_plateforme=payment.montant - dec - aut)
    else:
        # Frais de dossier (candidatures, relevés, attestations) : intégralement au décanat — règle à valider.
        RevenueEntry.objects.create(payment=payment, part_decanat=payment.montant, part_auteurs=0, part_plateforme=0)
        for rel in ("candidature", "demande"):
            obj = getattr(payment, rel, None)
            if obj is not None:
                obj.on_paid()
    return payment


def start_payment(payment):
    """Lance le paiement CinetPay pour un Payment en attente. -> dict de réponse API (payment_url, ou mock=True).

    Lève cinetpay.PaymentError si CinetPay refuse ou est injoignable (le Payment est alors marqué échoué).
    """
    from . import cinetpay

    label = payment.label or (str(payment.plan) if payment.plan_id else "Paiement UFR SEG")
    try:
        res = cinetpay.init_payment(payment, label)
    except cinetpay.PaymentError:
        payment.status = payment.Status.FAILED
        payment.save(update_fields=["status"])
        raise
    payment.provider_ref = res.reference
    payment.save(update_fields=["provider_ref"])
    return {"reference": str(payment.reference), "montant": payment.montant, "provider": payment.provider, "status": payment.status,
            "payment_url": res.redirect_url, "mock": res.mock}


def finalize_payment(payment):
    """Re-vérifie auprès de CinetPay (jamais sur la foi du navigateur ou du webhook) puis confirme ou échoue."""
    from . import cinetpay

    if payment.status != payment.Status.PENDING or not payment.provider_ref:
        return payment
    state, _raw = cinetpay.verify_payment(payment.provider_ref)
    if state == "succeeded":
        return confirm_payment(payment, provider_ref=payment.provider_ref)
    if state == "failed":
        payment.status = payment.Status.FAILED
        payment.save(update_fields=["status"])
    return payment


def create_fee_payment(user, montant, provider, phone, purpose, label):
    """Crée un paiement en attente pour des frais de dossier (à lancer ensuite avec start_payment)."""
    from .models import Payment
    from apps.accounts.models import normalize_phone

    if provider not in Payment.Provider.values:
        raise ValueError("Moyen de paiement invalide.")
    return Payment.objects.create(user=user, plan=None, purpose=purpose, label=label, montant=montant, provider=provider,
                                  payer_phone=normalize_phone(phone or user.phone))


def record_access(user, document, kind: str):
    """Enregistre un gain auteur si l'accès est qualifié (lecteur ≠ auteur, abonné, une fois/jour)."""
    if not document.auteur_id or document.auteur_id == user.id:
        return None
    rule = RemunerationRule.objects.filter(categorie=document.categorie).first()
    montant = 0
    if rule:
        montant = rule.par_telechargement if kind == "DOWNLOAD" else rule.par_consultation
    else:
        montant = 5 if kind == "DOWNLOAD" else 2
    earning, _ = AuthorEarning.objects.get_or_create(
        document=document, lecteur=user, type=kind, jour=timezone.localdate(),
        defaults={"auteur_id": document.auteur_id, "montant": montant},
    )
    return earning


def author_balance(user):
    agg = AuthorEarning.objects.filter(auteur=user)
    total = agg.aggregate(s=Sum("montant"))["s"] or 0
    disponible = agg.filter(payout__isnull=True).aggregate(s=Sum("montant"))["s"] or 0
    return {"total": float(total), "disponible": float(disponible), "verse": float(total) - float(disponible)}
