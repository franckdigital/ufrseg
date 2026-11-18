import uuid

from django.conf import settings
from django.db import models


def new_ref():
    return "UFR-" + uuid.uuid4().hex[:8].upper()


class Demande(models.Model):
    """Démarche administrative dématérialisée (autorisation, réintégration, attestation, réclamation…)."""

    class Type(models.TextChoices):
        AUTORISATION_ABSENCE = "ABSENCE", "Autorisation d'absence"
        AUTORISATION_EVENEMENT = "EVENEMENT", "Participation à un événement"
        AUTORISATION_RECHERCHE = "RECHERCHE", "Autorisation de recherche / collecte de données"
        AUTORISATION_SOUTENANCE = "SOUTENANCE", "Autorisation de soutenance"
        REINTEGRATION = "REINTEGRATION", "Réintégration"
        INSCRIPTION = "INSCRIPTION", "Inscription / réinscription"
        CHANGEMENT_PARCOURS = "PARCOURS", "Changement de parcours"
        ATT_SCOLARITE = "ATT_SCOLARITE", "Attestation de scolarité"
        RELEVE = "RELEVE", "Relevé de notes"
        BULLETIN = "BULLETIN", "Bulletin de notes"
        ATT_ADMISSION = "ATT_ADMISS", "Attestation provisoire d'admission"
        CERT_FREQUENTATION = "CERT_FREQ", "Certificat de fréquentation"
        ATT_REUSSITE = "ATT_REUSSITE", "Attestation de réussite"
        RECLAMATION_NOTE = "REC_NOTE", "Réclamation de note"
        RECLAMATION_AUTRE = "REC_AUTRE", "Autre réclamation"

    class Statut(models.TextChoices):
        PAIEMENT = "PAIEMENT", "En attente de paiement"
        SOUMISE = "SOUMISE", "Soumise"
        EN_VERIFICATION = "VERIF", "En vérification"
        EN_TRAITEMENT = "TRAITEMENT", "En traitement"
        APPROUVEE = "APPROUVEE", "Approuvée"
        REJETEE = "REJETEE", "Rejetée"
        CLOTUREE = "CLOTUREE", "Clôturée"

    reference = models.CharField(max_length=16, unique=True, default=new_ref, editable=False)
    demandeur = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="demandes")
    type = models.CharField(max_length=14, choices=Type.choices)
    annee_academique = models.CharField(max_length=9, blank=True, help_text="Année concernée (relevés, bulletins)")
    montant = models.PositiveIntegerField(default=0)
    paiement = models.OneToOneField("billing.Payment", null=True, blank=True, on_delete=models.SET_NULL, related_name="demande")
    objet = models.CharField(max_length=200)
    details = models.TextField(blank=True)
    piece_jointe = models.FileField(upload_to="demandes/", null=True, blank=True)
    statut = models.CharField(max_length=10, choices=Statut.choices, default=Statut.SOUMISE)
    observations = models.TextField(blank=True)
    traite_par = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created = models.DateTimeField(auto_now_add=True)
    cloturee_le = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created"]

    SERVICE = {
        "ATT_SCOLARITE": "Scolarité", "RELEVE": "Scolarité", "BULLETIN": "Scolarité", "ATT_ADMISS": "Scolarité", "CERT_FREQ": "Scolarité", "ATT_REUSSITE": "Scolarité",
        "INSCRIPTION": "Scolarité", "PARCOURS": "Scolarité", "REC_NOTE": "Scolarité",
    }

    def on_paid(self):
        if self.statut == self.Statut.PAIEMENT:
            self.statut = self.Statut.SOUMISE
            self.save(update_fields=["statut"])

    @property
    def service(self):
        return self.SERVICE.get(self.type, "Décanat")

    def __str__(self):
        return f"{self.reference} · {self.get_type_display()}"


class RendezVous(models.Model):
    class Avec(models.TextChoices):
        DECANAT = "DECANAT", "Décanat"
        SCOLARITE = "SCOLARITE", "Scolarité"
        RESPONSABLE = "RESPONSABLE", "Responsable pédagogique"
        ENSEIGNANT = "ENSEIGNANT", "Enseignant"

    class Statut(models.TextChoices):
        DEMANDE = "DEMANDE", "Demandé"
        CONFIRME = "CONFIRME", "Confirmé"
        ANNULE = "ANNULE", "Annulé"

    etudiant = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="rendez_vous")
    avec = models.CharField(max_length=12, choices=Avec.choices)
    motif = models.CharField(max_length=200)
    date_souhaitee = models.DateTimeField()
    date_confirmee = models.DateTimeField(null=True, blank=True)
    statut = models.CharField(max_length=8, choices=Statut.choices, default=Statut.DEMANDE)

    class Meta:
        ordering = ["-date_souhaitee"]
        verbose_name_plural = "Rendez-vous"


class FraisService(models.Model):
    """Frais de traitement de dossier par type de démarche (FCFA) — modifiable par le décanat."""

    type = models.CharField(max_length=14, unique=True, choices=Demande.Type.choices)
    montant = models.PositiveIntegerField()

    def __str__(self):
        return f"{self.get_type_display()} : {self.montant} FCFA"
