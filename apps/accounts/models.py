import re

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models


def normalize_phone(raw: str) -> str:
    """Normalise un numéro ivoirien en +225XXXXXXXXXX (10 chiffres locaux)."""
    digits = re.sub(r"\D", "", raw or "")
    if digits.startswith("225") and len(digits) == 13:
        digits = digits[3:]
    if len(digits) != 10:
        raise ValueError("Le numéro doit contenir 10 chiffres (ex: 0707070707).")
    return f"+225{digits}"


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create(self, phone, password, **extra):
        if not phone:
            raise ValueError("Le numéro de téléphone est obligatoire.")
        phone = normalize_phone(phone)
        email = extra.pop("email", None) or None
        if email:
            email = self.normalize_email(email)
        user = self.model(phone=phone, email=email, **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, phone, password=None, **extra):
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create(phone, password, **extra)

    def create_superuser(self, phone, password=None, **extra):
        extra.update(is_staff=True, is_superuser=True, role=User.Role.ADMIN)
        return self._create(phone, password, **extra)


class User(AbstractBaseUser, PermissionsMixin):
    class Role(models.TextChoices):
        ADMIN = "ADMIN", "Administrateur général"
        DECANAT = "DECANAT", "Décanat"
        SCOLARITE = "SCOLARITE", "Scolarité"
        ENSEIGNANT = "ENSEIGNANT", "Enseignant"
        ETUDIANT = "ETUDIANT", "Étudiant"

    phone = models.CharField("Téléphone", max_length=16, unique=True)
    email = models.EmailField(unique=True, null=True, blank=True)
    first_name = models.CharField("Prénom", max_length=80)
    last_name = models.CharField("Nom", max_length=80)
    role = models.CharField(max_length=12, choices=Role.choices, default=Role.ETUDIANT)
    matricule = models.CharField(max_length=30, blank=True, db_index=True)
    is_author = models.BooleanField("Auteur contributeur", default=False)
    is_class_rep = models.BooleanField("Responsable de classe", default=False)
    classe = models.ForeignKey("academics.Classe", null=True, blank=True, on_delete=models.SET_NULL, related_name="etudiants")
    avatar = models.ImageField(upload_to="avatars/", null=True, blank=True)
    has_pin = models.BooleanField(default=False)
    registered_by_voice = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(auto_now_add=True)

    USERNAME_FIELD = "phone"
    REQUIRED_FIELDS = ["first_name", "last_name"]
    objects = UserManager()

    class Meta:
        ordering = ["last_name", "first_name"]

    def __str__(self):
        return f"{self.first_name} {self.last_name}".strip() or self.phone

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def is_dean_staff(self):
        return self.role in (self.Role.ADMIN, self.Role.DECANAT)

    @property
    def is_back_office(self):
        return self.role in (self.Role.ADMIN, self.Role.DECANAT, self.Role.SCOLARITE)
