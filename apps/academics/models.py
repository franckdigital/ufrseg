from django.conf import settings
from django.db import models


class AnneeAcademique(models.Model):
    libelle = models.CharField(max_length=9, unique=True, help_text="ex: 2025-2026")
    debut = models.DateField()
    fin = models.DateField()
    active = models.BooleanField(default=False)

    class Meta:
        ordering = ["-debut"]
        verbose_name = "Année académique"
        verbose_name_plural = "Années académiques"

    def save(self, *a, **kw):
        super().save(*a, **kw)
        if self.active:
            AnneeAcademique.objects.exclude(pk=self.pk).update(active=False)

    def __str__(self):
        return self.libelle


class Filiere(models.Model):
    code = models.CharField(max_length=12, unique=True)
    nom = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    debouches = models.TextField(blank=True)
    conditions_admission = models.TextField(blank=True)

    class Meta:
        ordering = ["nom"]

    def __str__(self):
        return self.nom


class Niveau(models.TextChoices):
    L1 = "L1", "Licence 1"
    L2 = "L2", "Licence 2"
    L3 = "L3", "Licence 3"
    M1 = "M1", "Master 1"
    M2 = "M2", "Master 2"


class Parcours(models.Model):
    filiere = models.ForeignKey(Filiere, on_delete=models.CASCADE, related_name="parcours")
    nom = models.CharField(max_length=160)

    class Meta:
        ordering = ["filiere", "nom"]
        verbose_name_plural = "Parcours"

    def __str__(self):
        return f"{self.filiere.code} · {self.nom}"


class Classe(models.Model):
    nom = models.CharField(max_length=120)
    filiere = models.ForeignKey(Filiere, on_delete=models.PROTECT, related_name="classes")
    parcours = models.ForeignKey(Parcours, null=True, blank=True, on_delete=models.SET_NULL)
    niveau = models.CharField(max_length=2, choices=Niveau.choices)
    annee = models.ForeignKey(AnneeAcademique, on_delete=models.PROTECT, related_name="classes")

    class Meta:
        ordering = ["-annee__debut", "niveau", "nom"]
        unique_together = [("nom", "annee")]

    def __str__(self):
        return f"{self.nom} ({self.annee})"


class UE(models.Model):
    class Type(models.TextChoices):
        OBLIGATOIRE = "OBL", "Obligatoire"
        OPTIONNELLE = "OPT", "Optionnelle"

    code = models.CharField(max_length=20)
    intitule = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    filiere = models.ForeignKey(Filiere, on_delete=models.CASCADE, related_name="ues")
    parcours = models.ForeignKey(Parcours, null=True, blank=True, on_delete=models.SET_NULL)
    niveau = models.CharField(max_length=2, choices=Niveau.choices)
    semestre = models.PositiveSmallIntegerField(help_text="1 à 6 (S1…S6)")
    credits = models.PositiveSmallIntegerField(default=6)
    coefficient = models.DecimalField(max_digits=4, decimal_places=2, default=1)
    type = models.CharField(max_length=3, choices=Type.choices, default=Type.OBLIGATOIRE)
    seuil_validation = models.DecimalField(max_digits=4, decimal_places=2, default=10, help_text="Moyenne minimale pour valider l'UE")
    note_eliminatoire = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True, help_text="Note plancher d'une ECUE (vide = compensation totale)")

    class Meta:
        ordering = ["niveau", "semestre", "code"]
        unique_together = [("code", "filiere")]
        verbose_name = "Unité d'enseignement"

    def __str__(self):
        return f"{self.code} — {self.intitule}"


class ECUE(models.Model):
    ue = models.ForeignKey(UE, on_delete=models.CASCADE, related_name="ecues")
    code = models.CharField(max_length=20)
    intitule = models.CharField(max_length=200)
    enseignant = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="ecues", limit_choices_to={"role": "ENSEIGNANT"})
    coefficient = models.DecimalField(max_digits=4, decimal_places=2, default=1)
    volume_horaire = models.PositiveSmallIntegerField(default=30)
    modalites = models.CharField(max_length=200, blank=True, help_text="ex: CC 40% + Examen 60%")
    prerequis = models.ManyToManyField("self", blank=True, symmetrical=False)

    class Meta:
        ordering = ["ue", "code"]
        unique_together = [("ue", "code")]
        verbose_name = "ECUE"

    def __str__(self):
        return f"{self.code} — {self.intitule}"


class RegleValidation(models.Model):
    """Règles officielles affichées dans le guide de validation (paramétrées par le décanat)."""

    filiere = models.ForeignKey(Filiere, null=True, blank=True, on_delete=models.CASCADE, help_text="Vide = règle générale")
    titre = models.CharField(max_length=160)
    contenu = models.TextField()
    ordre = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["ordre", "id"]
        verbose_name = "Règle de validation"

    def __str__(self):
        return self.titre
