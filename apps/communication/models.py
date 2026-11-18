from django.conf import settings
from django.db import models


class Annonce(models.Model):
    class Categorie(models.TextChoices):
        RENTREE = "RENTREE", "Rentrée"
        EXAMENS = "EXAMENS", "Examens"
        RESULTATS = "RESULTATS", "Résultats"
        ADMIN = "ADMIN", "Administratif"
        EVENEMENT = "EVENEMENT", "Événement"
        BOURSE = "BOURSE", "Bourses"
        STAGE = "STAGE", "Stages & emploi"

    titre = models.CharField(max_length=200)
    categorie = models.CharField(max_length=10, choices=Categorie.choices, default=Categorie.ADMIN)
    resume = models.CharField(max_length=300, blank=True)
    contenu = models.TextField()
    image = models.ImageField(upload_to="annonces/", null=True, blank=True)
    niveau = models.CharField(max_length=2, blank=True, help_text="Vide = tous niveaux")
    publie = models.BooleanField(default=True)
    epingle = models.BooleanField(default=False)
    auteur = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-epingle", "-created"]


class Evenement(models.Model):
    class Type(models.TextChoices):
        RENTREE = "RENTREE", "Rentrée"
        COURS = "COURS", "Cours"
        TD = "TD", "TD"
        DEVOIR = "DEVOIR", "Devoir"
        EXAMEN = "EXAMEN", "Examen"
        RATTRAPAGE = "RATTRAPAGE", "Rattrapage"
        VACANCES = "VACANCES", "Vacances"
        DEPOT = "DEPOT", "Date limite de dépôt"
        SOUTENANCE = "SOUTENANCE", "Soutenance"
        AUTRE = "AUTRE", "Événement UFR"

    titre = models.CharField(max_length=200)
    type = models.CharField(max_length=10, choices=Type.choices, default=Type.AUTRE)
    debut = models.DateTimeField()
    fin = models.DateTimeField(null=True, blank=True)
    lieu = models.CharField(max_length=120, blank=True)
    description = models.TextField(blank=True)
    niveau = models.CharField(max_length=2, blank=True)
    classe = models.ForeignKey("academics.Classe", null=True, blank=True, on_delete=models.CASCADE)

    class Meta:
        ordering = ["debut"]


class Notification(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    titre = models.CharField(max_length=160)
    message = models.CharField(max_length=400, blank=True)
    lien = models.CharField(max_length=200, blank=True)
    lue = models.BooleanField(default=False)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created"]


class FAQ(models.Model):
    categorie = models.CharField(max_length=60, default="Général")
    question = models.CharField(max_length=300)
    reponse = models.TextField()
    ordre = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["categorie", "ordre"]
        verbose_name = "FAQ"
        verbose_name_plural = "FAQ"


class ContactMessage(models.Model):
    nom = models.CharField(max_length=120)
    email = models.EmailField()
    sujet = models.CharField(max_length=160)
    message = models.TextField()
    traite = models.BooleanField(default=False)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created"]


class Offre(models.Model):
    class Type(models.TextChoices):
        STAGE = "STAGE", "Stage"
        EMPLOI = "EMPLOI", "Emploi"
        FORMATION = "FORMATION", "Formation"
        RECHERCHE = "RECHERCHE", "Recherche"

    titre = models.CharField(max_length=200)
    type = models.CharField(max_length=10, choices=Type.choices, default=Type.STAGE)
    organisation = models.CharField(max_length=160)
    lieu = models.CharField(max_length=120, blank=True)
    description = models.TextField()
    date_limite = models.DateField(null=True, blank=True)
    actif = models.BooleanField(default=True)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created"]
