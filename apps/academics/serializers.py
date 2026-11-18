from rest_framework import serializers

from .models import ECUE, UE, AnneeAcademique, Classe, Filiere, Parcours, RegleValidation


class AnneeSerializer(serializers.ModelSerializer):
    class Meta:
        model = AnneeAcademique
        fields = "__all__"


class ParcoursSerializer(serializers.ModelSerializer):
    class Meta:
        model = Parcours
        fields = "__all__"


class FiliereSerializer(serializers.ModelSerializer):
    parcours = ParcoursSerializer(many=True, read_only=True)

    class Meta:
        model = Filiere
        fields = "__all__"


class ClasseSerializer(serializers.ModelSerializer):
    filiere_nom = serializers.CharField(source="filiere.nom", read_only=True)
    annee_libelle = serializers.CharField(source="annee.libelle", read_only=True)
    effectif = serializers.IntegerField(source="etudiants.count", read_only=True)

    class Meta:
        model = Classe
        fields = "__all__"


class ECUESerializer(serializers.ModelSerializer):
    enseignant_nom = serializers.CharField(source="enseignant.full_name", read_only=True, default=None)

    class Meta:
        model = ECUE
        fields = "__all__"


class UESerializer(serializers.ModelSerializer):
    ecues = ECUESerializer(many=True, read_only=True)

    class Meta:
        model = UE
        fields = "__all__"


class RegleSerializer(serializers.ModelSerializer):
    class Meta:
        model = RegleValidation
        fields = "__all__"
