from django.conf import settings
from django.db import models


class Guide(models.Model):
    """Contenu éditorial du parcours : orientation, inscription, cursus L1→Doctorat, sélection Master, Doctorat."""

    class Categorie(models.TextChoices):
        ORIENTATION = "ORIENTATION", "Orientation des nouveaux bacheliers"
        INSCRIPTION = "INSCRIPTION", "Processus d'inscription"
        PARCOURS = "PARCOURS", "Parcours académique (L1 → Doctorat)"
        MASTER = "MASTER", "Sélection en Master 1"
        DOCTORAT = "DOCTORAT", "Doctorat"

    categorie = models.CharField(max_length=12, choices=Categorie.choices)
    titre = models.CharField(max_length=160)
    resume = models.CharField(max_length=300, blank=True)
    contenu = models.TextField(help_text="Texte libre. Une ligne commençant par « - » devient une puce.")
    icone = models.CharField(max_length=30, blank=True)
    ordre = models.PositiveSmallIntegerField(default=0)
    publie = models.BooleanField(default=True)

    class Meta:
        ordering = ["categorie", "ordre", "id"]

    def __str__(self):
        return f"[{self.categorie}] {self.titre}"


class Programme(models.Model):
    """Offre de Master 1 ou de Doctorat ouverte à candidature."""

    class Niveau(models.TextChoices):
        M1 = "M1", "Master 1"
        DOCTORAT = "DOC", "Doctorat"

    class Type(models.TextChoices):
        RECHERCHE = "RECHERCHE", "Master recherche"
        PROFESSIONNEL = "PRO", "Master professionnel / appliqué"
        DOCTORAT = "DOC", "Doctorat"

    niveau = models.CharField(max_length=3, choices=Niveau.choices, default=Niveau.M1)
    type = models.CharField(max_length=10, choices=Type.choices, default=Type.PROFESSIONNEL)
    nom = models.CharField(max_length=160)
    filiere = models.ForeignKey("academics.Filiere", null=True, blank=True, on_delete=models.SET_NULL)
    description = models.TextField(blank=True)
    debouches = models.TextField(blank=True)
    criteres = models.TextField(blank=True, help_text="Critères de sélection, une ligne par critère")
    pieces = models.TextField(blank=True, help_text="Pièces à fournir, une ligne par pièce")
    capacite = models.PositiveSmallIntegerField(default=40)
    frais_dossier = models.PositiveIntegerField(default=10000, help_text="Frais de traitement du dossier (FCFA)")
    date_limite = models.DateField(null=True, blank=True)
    ouvert = models.BooleanField(default=True)

    class Meta:
        ordering = ["niveau", "nom"]

    def __str__(self):
        return f"{self.get_niveau_display()} · {self.nom}"


class Candidature(models.Model):
    class Statut(models.TextChoices):
        BROUILLON = "BROUILLON", "Brouillon (paiement en attente)"
        SOUMISE = "SOUMISE", "Soumise"
        EN_ETUDE = "EN_ETUDE", "En étude"
        ENTRETIEN = "ENTRETIEN", "Convoqué à l'entretien"
        ADMIS = "ADMIS", "Admis"
        LISTE_ATTENTE = "ATTENTE", "Liste d'attente"
        REFUSE = "REFUSE", "Non retenu"

    reference = models.CharField(max_length=16, unique=True, editable=False)
    candidat = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="candidatures")
    programme = models.ForeignKey(Programme, on_delete=models.PROTECT, related_name="candidatures")
    annee = models.CharField(max_length=9, default="2025-2026")
    licence_intitule = models.CharField("Licence obtenue / en cours", max_length=200)
    licence_etablissement = models.CharField(max_length=200, default="UFR SEG — UFHB")
    moyenne_l1 = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    moyenne_l2 = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    moyenne_l3 = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    annees_redoublees = models.PositiveSmallIntegerField(default=0)
    motivation = models.TextField()
    sujet_recherche = models.TextField(blank=True, help_text="Projet de thèse (doctorat) ou thème de mémoire envisagé")
    directeur_envisage = models.CharField(max_length=160, blank=True)
    cv = models.FileField(upload_to="candidatures/", null=True, blank=True)
    releves = models.FileField(upload_to="candidatures/", null=True, blank=True)
    statut = models.CharField(max_length=10, choices=Statut.choices, default=Statut.BROUILLON)
    montant = models.PositiveIntegerField(default=0)
    paiement = models.OneToOneField("billing.Payment", null=True, blank=True, on_delete=models.SET_NULL, related_name="candidature")
    observations = models.TextField(blank=True)
    decide_par = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created"]
        unique_together = [("candidat", "programme", "annee")]

    def save(self, *a, **kw):
        if not self.reference:
            import uuid
            self.reference = "CAND-" + uuid.uuid4().hex[:8].upper()
        super().save(*a, **kw)

    def on_paid(self):
        if self.statut == self.Statut.BROUILLON:
            self.statut = self.Statut.SOUMISE
            self.save(update_fields=["statut"])

    @property
    def moyenne_generale(self):
        vals = [v for v in (self.moyenne_l1, self.moyenne_l2, self.moyenne_l3) if v is not None]
        return round(sum(vals) / len(vals), 2) if vals else None

    def __str__(self):
        return f"{self.reference} · {self.candidat}"
