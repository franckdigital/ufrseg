from django.conf import settings
from django.db import models

User = settings.AUTH_USER_MODEL


class Groupe(models.Model):
    classe = models.ForeignKey("academics.Classe", on_delete=models.CASCADE, related_name="groupes")
    nom = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    responsable = models.ForeignKey(User, null=True, on_delete=models.SET_NULL, related_name="groupes_diriges")
    ue = models.ForeignKey("academics.UE", null=True, blank=True, on_delete=models.SET_NULL)
    max_membres = models.PositiveSmallIntegerField(default=6)
    created = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.nom


class MembreGroupe(models.Model):
    class Statut(models.TextChoices):
        INVITE = "INVITE", "Invité"
        ACTIF = "ACTIF", "Membre"

    groupe = models.ForeignKey(Groupe, on_delete=models.CASCADE, related_name="membres")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="appartenances")
    statut = models.CharField(max_length=6, choices=Statut.choices, default=Statut.ACTIF)

    class Meta:
        unique_together = [("groupe", "user")]


class MessageGroupe(models.Model):
    groupe = models.ForeignKey(Groupe, on_delete=models.CASCADE, related_name="messages")
    auteur = models.ForeignKey(User, on_delete=models.CASCADE)
    texte = models.TextField()
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created"]


class Devoir(models.Model):
    """TD / devoir à rendre (individuel ou en groupe)."""

    classe = models.ForeignKey("academics.Classe", on_delete=models.CASCADE, related_name="devoirs")
    ecue = models.ForeignKey("academics.ECUE", null=True, blank=True, on_delete=models.SET_NULL)
    titre = models.CharField(max_length=200)
    enonce = models.TextField()
    fichier = models.FileField(upload_to="devoirs/", null=True, blank=True)
    date_limite = models.DateTimeField()
    en_groupe = models.BooleanField(default=False)
    bareme = models.PositiveSmallIntegerField(default=20)
    cree_par = models.ForeignKey(User, on_delete=models.CASCADE, related_name="devoirs_crees")
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date_limite"]


class Soumission(models.Model):
    devoir = models.ForeignKey(Devoir, on_delete=models.CASCADE, related_name="soumissions")
    auteur = models.ForeignKey(User, on_delete=models.CASCADE, related_name="soumissions")
    groupe = models.ForeignKey(Groupe, null=True, blank=True, on_delete=models.SET_NULL)
    fichier = models.FileField(upload_to="soumissions/")
    commentaire = models.TextField(blank=True)
    en_retard = models.BooleanField(default=False)
    note = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    appreciation = models.TextField(blank=True)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("devoir", "auteur")]


class Evaluation(models.Model):
    class Type(models.TextChoices):
        DEVOIR = "DEVOIR", "Devoir"
        INTERRO = "INTERRO", "Interrogation"
        BLANC = "BLANC", "Examen blanc"
        EXAMEN = "EXAMEN", "Examen"
        ENTRAINEMENT = "TRAIN", "Test d'entraînement"

    classe = models.ForeignKey("academics.Classe", on_delete=models.CASCADE, related_name="evaluations")
    ecue = models.ForeignKey("academics.ECUE", null=True, blank=True, on_delete=models.SET_NULL)
    titre = models.CharField(max_length=200)
    type = models.CharField(max_length=8, choices=Type.choices, default=Type.DEVOIR)
    consignes = models.TextField(blank=True)
    duree_min = models.PositiveSmallIntegerField(default=60)
    debut = models.DateTimeField()
    fin = models.DateTimeField()
    tentatives_max = models.PositiveSmallIntegerField(default=1)
    melanger_questions = models.BooleanField(default=True)
    publie = models.BooleanField(default=False, help_text="Visible par les étudiants")
    resultats_publies = models.BooleanField(default=False)
    cree_par = models.ForeignKey(User, on_delete=models.CASCADE, related_name="evaluations_creees")
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-debut"]

    def total_points(self):
        return sum(q.bareme for q in self.questions.all())


class Question(models.Model):
    class Type(models.TextChoices):
        QCM = "QCM", "Choix unique"
        MULTI = "MULTI", "Choix multiples"
        VF = "VF", "Vrai / Faux"
        TROUS = "TROUS", "Texte à trous"
        NUM = "NUM", "Numérique"
        OUVERTE = "OUVERTE", "Question ouverte"

    evaluation = models.ForeignKey(Evaluation, on_delete=models.CASCADE, related_name="questions")
    type = models.CharField(max_length=7, choices=Type.choices)
    enonce = models.TextField()
    options = models.JSONField(default=list, blank=True, help_text="Liste des choix (QCM/MULTI)")
    reponse = models.JSONField(null=True, blank=True, help_text="QCM: index; MULTI: [index]; VF: bool; TROUS: [réponses acceptées]; NUM: {valeur, tolerance}")
    bareme = models.DecimalField(max_digits=5, decimal_places=2, default=1)
    explication = models.TextField(blank=True)
    ordre = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["ordre", "id"]


class Copie(models.Model):
    class Statut(models.TextChoices):
        EN_COURS = "EN_COURS", "En cours"
        SOUMISE = "SOUMISE", "Soumise"
        CORRIGEE = "CORRIGEE", "Corrigée"

    evaluation = models.ForeignKey(Evaluation, on_delete=models.CASCADE, related_name="copies")
    etudiant = models.ForeignKey(User, on_delete=models.CASCADE, related_name="copies")
    tentative = models.PositiveSmallIntegerField(default=1)
    reponses = models.JSONField(default=dict, blank=True)  # {question_id: valeur}
    detail_notes = models.JSONField(default=dict, blank=True)  # {question_id: points}
    debut = models.DateTimeField(auto_now_add=True)
    soumise_le = models.DateTimeField(null=True, blank=True)
    statut = models.CharField(max_length=8, choices=Statut.choices, default=Statut.EN_COURS)
    note_auto = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    note_finale = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    commentaire = models.TextField(blank=True)
    evenements = models.JSONField(default=list, blank=True, help_text="Journal anti-fraude (perte de focus, etc.)")

    class Meta:
        unique_together = [("evaluation", "etudiant", "tentative")]


class Note(models.Model):
    """Note saisie par l'enseignant pour une ECUE."""

    class Type(models.TextChoices):
        CC = "CC", "Contrôle continu"
        TD = "TD", "Travaux dirigés"
        EXAMEN = "EXAMEN", "Examen"
        RATTRAPAGE = "RATTRAPAGE", "Rattrapage"

    etudiant = models.ForeignKey(User, on_delete=models.CASCADE, related_name="notes")
    ecue = models.ForeignKey("academics.ECUE", on_delete=models.CASCADE, related_name="notes")
    annee = models.ForeignKey("academics.AnneeAcademique", on_delete=models.PROTECT)
    type = models.CharField(max_length=10, choices=Type.choices, default=Type.EXAMEN)
    valeur = models.DecimalField(max_digits=4, decimal_places=2)
    appreciation = models.CharField(max_length=200, blank=True)
    publiee = models.BooleanField(default=False)
    saisie_par = models.ForeignKey(User, null=True, on_delete=models.SET_NULL, related_name="+")
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("etudiant", "ecue", "annee", "type")]
        ordering = ["-created"]
