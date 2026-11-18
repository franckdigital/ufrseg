from django.conf import settings
from django.db import models


class Document(models.Model):
    class Categorie(models.TextChoices):
        MEMOIRE = "MEMOIRE", "Mémoire"
        DEVOIR = "DEVOIR", "Devoir"
        TD = "TD", "Travaux dirigés"
        EXAMEN = "EXAMEN", "Examen"
        CORRECTION = "CORRECTION", "Correction"
        SUPPORT = "SUPPORT", "Support pédagogique"

    class Statut(models.TextChoices):
        SOUMIS = "SOUMIS", "Soumis"
        EN_REVISION = "REVISION", "En révision"
        PUBLIE = "PUBLIE", "Publié"
        REJETE = "REJETE", "Rejeté"
        SUSPENDU = "SUSPENDU", "Suspendu"

    titre = models.CharField(max_length=220)
    description = models.TextField(blank=True)
    categorie = models.CharField(max_length=12, choices=Categorie.choices)
    fichier = models.FileField(upload_to="documents/%Y/%m/")
    taille = models.PositiveIntegerField(default=0)
    filiere = models.ForeignKey("academics.Filiere", null=True, blank=True, on_delete=models.SET_NULL)
    niveau = models.CharField(max_length=2, blank=True)
    annee = models.ForeignKey("academics.AnneeAcademique", null=True, blank=True, on_delete=models.SET_NULL)
    semestre = models.PositiveSmallIntegerField(null=True, blank=True)
    ue = models.ForeignKey("academics.UE", null=True, blank=True, on_delete=models.SET_NULL, related_name="documents")
    ecue = models.ForeignKey("academics.ECUE", null=True, blank=True, on_delete=models.SET_NULL, related_name="documents")
    auteur = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="documents_ecrits")
    document_lie = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="corrections", help_text="Sujet auquel se rapporte une correction")
    statut = models.CharField(max_length=8, choices=Statut.choices, default=Statut.SOUMIS)
    motif_rejet = models.CharField(max_length=300, blank=True)
    apercu_gratuit = models.BooleanField(default=False, help_text="Visible sans abonnement (aperçu)")
    created = models.DateTimeField(auto_now_add=True)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created"]

    def __str__(self):
        return self.titre

    @property
    def is_premium(self):
        """Les corrections sont réservées au Pack Premium."""
        return self.categorie == self.Categorie.CORRECTION

    @property
    def a_correction(self):
        return self.corrections.filter(statut=self.Statut.PUBLIE).exists()


class DocumentAccess(models.Model):
    class Kind(models.TextChoices):
        VIEW = "VIEW", "Consultation"
        DOWNLOAD = "DOWNLOAD", "Téléchargement"

    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="accesses")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="accesses")
    kind = models.CharField(max_length=8, choices=Kind.choices)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created"]


class Favorite(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="favoris")
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="favoris")

    class Meta:
        unique_together = [("user", "document")]


class Review(models.Model):
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="avis")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    note = models.PositiveSmallIntegerField()
    commentaire = models.CharField(max_length=300, blank=True)
    signalement = models.BooleanField(default=False, help_text="Signalement d'erreur")

    class Meta:
        unique_together = [("user", "document")]
