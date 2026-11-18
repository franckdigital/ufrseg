import uuid
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone


class Plan(models.Model):
    class Pack(models.TextChoices):
        ESSENTIEL = "ESSENTIEL", "Pack Essentiel"
        PREMIUM = "PREMIUM", "Pack Premium"

    class Duree(models.IntegerChoices):
        MENSUEL = 1, "1 mois"
        TRIMESTRIEL = 3, "3 mois"
        SEMESTRIEL = 6, "6 mois"
        ANNUEL = 12, "12 mois"

    pack = models.CharField(max_length=10, choices=Pack.choices)
    mois = models.PositiveSmallIntegerField(choices=Duree.choices)
    prix = models.PositiveIntegerField(help_text="FCFA")
    actif = models.BooleanField(default=True)

    class Meta:
        unique_together = [("pack", "mois")]
        ordering = ["pack", "mois"]

    def __str__(self):
        return f"{self.get_pack_display()} · {self.mois} mois · {self.prix} FCFA"


class Subscription(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="subscriptions")
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT)
    debut = models.DateTimeField(default=timezone.now)
    fin = models.DateTimeField()
    annule = models.BooleanField(default=False)

    class Meta:
        ordering = ["-fin"]

    @property
    def active(self):
        return not self.annule and self.fin > timezone.now()

    def __str__(self):
        return f"{self.user} → {self.plan}"


def active_subscription(user):
    """Abonnement valide le plus favorable (Premium prioritaire)."""
    if not user or not user.is_authenticated:
        return None
    subs = [s for s in user.subscriptions.select_related("plan").filter(annule=False, fin__gt=timezone.now())]
    subs.sort(key=lambda s: (s.plan.pack == Plan.Pack.PREMIUM, s.fin), reverse=True)
    return subs[0] if subs else None


class Payment(models.Model):
    class Provider(models.TextChoices):
        ORANGE = "ORANGE", "Orange Money"
        MTN = "MTN", "MTN Mobile Money"
        MOOV = "MOOV", "Moov Money"
        WAVE = "WAVE", "Wave"
        CARD = "CARD", "Carte bancaire"

    class Status(models.TextChoices):
        PENDING = "PENDING", "En attente"
        SUCCESS = "SUCCESS", "Confirmé"
        FAILED = "FAILED", "Échoué"
        REFUNDED = "REFUNDED", "Remboursé"

    reference = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="payments")
    plan = models.ForeignKey(Plan, null=True, blank=True, on_delete=models.PROTECT)
    purpose = models.CharField(max_length=12, default="ABONNEMENT", choices=[("ABONNEMENT", "Abonnement"), ("CANDIDATURE", "Frais de candidature"), ("DEMANDE", "Frais de dossier")])
    label = models.CharField(max_length=160, blank=True)
    montant = models.PositiveIntegerField()
    provider = models.CharField(max_length=8, choices=Provider.choices)
    payer_phone = models.CharField(max_length=16, blank=True)
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.PENDING)
    provider_ref = models.CharField(max_length=80, blank=True)
    created = models.DateTimeField(auto_now_add=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created"]

    def __str__(self):
        return f"{self.reference} {self.montant} FCFA {self.status}"


class RevenueSplit(models.Model):
    """Clé de répartition des recettes — le plus récent enregistrement actif s'applique."""

    decanat = models.PositiveSmallIntegerField(default=40)
    auteurs = models.PositiveSmallIntegerField(default=40)
    plateforme = models.PositiveSmallIntegerField(default=20)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created"]

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.decanat + self.auteurs + self.plateforme != 100:
            raise ValidationError("La somme des pourcentages doit être égale à 100.")

    def save(self, *a, **kw):
        self.full_clean()
        super().save(*a, **kw)

    @classmethod
    def current(cls):
        return cls.objects.first() or cls(**settings.DEFAULT_REVENUE_SPLIT)


class RevenueEntry(models.Model):
    """Ventilation d'un paiement confirmé."""

    payment = models.OneToOneField(Payment, on_delete=models.CASCADE, related_name="ventilation")
    part_decanat = models.PositiveIntegerField()
    part_auteurs = models.PositiveIntegerField()
    part_plateforme = models.PositiveIntegerField()
    created = models.DateTimeField(auto_now_add=True)


class RemunerationRule(models.Model):
    """Barème de rémunération des auteurs par catégorie de document (FCFA)."""

    categorie = models.CharField(max_length=12, unique=True)
    par_consultation = models.DecimalField(max_digits=8, decimal_places=2, default=2)
    par_telechargement = models.DecimalField(max_digits=8, decimal_places=2, default=5)

    def __str__(self):
        return self.categorie


class AuthorEarning(models.Model):
    """Gain généré par une consultation/téléchargement qualifié (dédoublonné par jour)."""

    auteur = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="earnings")
    document = models.ForeignKey("library.Document", on_delete=models.CASCADE, related_name="earnings")
    lecteur = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    type = models.CharField(max_length=8)  # VIEW | DOWNLOAD
    montant = models.DecimalField(max_digits=8, decimal_places=2)
    jour = models.DateField(default=timezone.localdate)
    payout = models.ForeignKey("Payout", null=True, blank=True, on_delete=models.SET_NULL, related_name="earnings")
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        # Un même lecteur ne génère qu'un gain par document, par type et par jour.
        unique_together = [("document", "lecteur", "type", "jour")]


class Payout(models.Model):
    class Status(models.TextChoices):
        REQUESTED = "REQUESTED", "Demandé"
        PAID = "PAID", "Payé"
        REJECTED = "REJECTED", "Rejeté"

    auteur = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="payouts")
    montant = models.PositiveIntegerField()
    provider = models.CharField(max_length=8, choices=Payment.Provider.choices)
    phone = models.CharField(max_length=16)
    status = models.CharField(max_length=9, choices=Status.choices, default=Status.REQUESTED)
    justificatif = models.CharField(max_length=120, blank=True)
    created = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created"]


def compute_end(start, mois):
    return start + timedelta(days=30 * mois)
