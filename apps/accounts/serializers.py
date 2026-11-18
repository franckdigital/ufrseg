import re

from django.contrib.auth import authenticate
from rest_framework import serializers

from .models import User, normalize_phone


class UserSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(read_only=True)
    classe_name = serializers.CharField(source="classe.nom", read_only=True, default=None)

    class Meta:
        model = User
        fields = [
            "id", "phone", "email", "first_name", "last_name", "full_name", "role", "matricule",
            "is_author", "is_class_rep", "classe", "classe_name", "avatar", "has_pin",
            "registered_by_voice", "is_active", "date_joined",
        ]
        read_only_fields = ["id", "role", "has_pin", "registered_by_voice", "date_joined", "is_active"]


class RegisterSerializer(serializers.Serializer):
    """Inscription étudiant : téléphone + code PIN (4 à 6 chiffres), éventuellement dictés à la voix."""

    first_name = serializers.CharField(max_length=80)
    last_name = serializers.CharField(max_length=80)
    phone = serializers.CharField()
    pin = serializers.CharField(write_only=True, min_length=4, max_length=6)
    email = serializers.EmailField(required=False, allow_blank=True)
    matricule = serializers.CharField(required=False, allow_blank=True)
    by_voice = serializers.BooleanField(required=False, default=False)

    def validate_phone(self, value):
        try:
            phone = normalize_phone(value)
        except ValueError as e:
            raise serializers.ValidationError(str(e))
        if User.objects.filter(phone=phone).exists():
            raise serializers.ValidationError("Ce numéro est déjà enregistré.")
        return phone

    def validate_pin(self, value):
        if not re.fullmatch(r"\d{4,6}", value):
            raise serializers.ValidationError("Le code PIN doit contenir 4 à 6 chiffres.")
        if len(set(value)) == 1:
            raise serializers.ValidationError("Choisissez un PIN moins évident.")
        return value

    def validate_email(self, value):
        if value and User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("Cet e-mail est déjà utilisé.")
        return value or None

    def create(self, data):
        user = User(
            phone=data["phone"], email=data.get("email"), first_name=data["first_name"].strip().title(),
            last_name=data["last_name"].strip().upper(), matricule=data.get("matricule", ""),
            role=User.Role.ETUDIANT, has_pin=True, registered_by_voice=data.get("by_voice", False),
        )
        user.set_password(data["pin"])
        user.save()
        return user


class LoginSerializer(serializers.Serializer):
    """`identifier` = téléphone ou e-mail ; `secret` = PIN (étudiants) ou mot de passe."""

    identifier = serializers.CharField()
    secret = serializers.CharField(write_only=True)

    def validate(self, attrs):
        ident = attrs["identifier"].strip()
        phone = None
        if "@" in ident:
            u = User.objects.filter(email__iexact=ident).first()
            phone = u.phone if u else None
        else:
            try:
                phone = normalize_phone(ident)
            except ValueError:
                phone = None
        user = authenticate(username=phone, password=attrs["secret"]) if phone else None
        if not user:
            raise serializers.ValidationError("Identifiants incorrects.")
        if not user.is_active:
            raise serializers.ValidationError("Compte désactivé.")
        attrs["user"] = user
        return attrs


class ChangeSecretSerializer(serializers.Serializer):
    old_secret = serializers.CharField()
    new_secret = serializers.CharField(min_length=4)
