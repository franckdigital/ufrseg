from decimal import Decimal

from django.db.models import Count
from rest_framework import permissions, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.permissions import IsBackOffice, ReadOnlyOrBackOffice

from .models import ECUE, UE, AnneeAcademique, Classe, Filiere, Parcours, RegleValidation
from .serializers import (AnneeSerializer, ClasseSerializer, ECUESerializer, FiliereSerializer,
                          ParcoursSerializer, RegleSerializer, UESerializer)


class PublicReadBackOfficeWrite(permissions.BasePermission):
    """Catalogue public en lecture (vitrine), écriture réservée au back-office."""

    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        u = request.user
        return bool(u and u.is_authenticated and u.is_back_office)


class AnneeViewSet(viewsets.ModelViewSet):
    queryset = AnneeAcademique.objects.all()
    serializer_class = AnneeSerializer
    permission_classes = [ReadOnlyOrBackOffice]


class FiliereViewSet(viewsets.ModelViewSet):
    queryset = Filiere.objects.prefetch_related("parcours")
    serializer_class = FiliereSerializer
    permission_classes = [PublicReadBackOfficeWrite]
    search_fields = ["nom", "code"]
    pagination_class = None


class ParcoursViewSet(viewsets.ModelViewSet):
    queryset = Parcours.objects.select_related("filiere")
    serializer_class = ParcoursSerializer
    permission_classes = [PublicReadBackOfficeWrite]
    filterset_fields = ["filiere"]
    pagination_class = None


class ClasseViewSet(viewsets.ModelViewSet):
    queryset = Classe.objects.select_related("filiere", "annee")
    serializer_class = ClasseSerializer
    permission_classes = [ReadOnlyOrBackOffice]
    filterset_fields = ["filiere", "niveau", "annee"]
    search_fields = ["nom"]


class UEViewSet(viewsets.ModelViewSet):
    queryset = UE.objects.prefetch_related("ecues__enseignant")
    serializer_class = UESerializer
    permission_classes = [PublicReadBackOfficeWrite]
    filterset_fields = ["filiere", "parcours", "niveau", "semestre", "type"]
    search_fields = ["code", "intitule"]


class ECUEViewSet(viewsets.ModelViewSet):
    queryset = ECUE.objects.select_related("ue", "enseignant")
    serializer_class = ECUESerializer
    permission_classes = [PublicReadBackOfficeWrite]
    filterset_fields = ["ue", "enseignant", "ue__niveau", "ue__semestre"]
    search_fields = ["code", "intitule"]


class RegleViewSet(viewsets.ModelViewSet):
    queryset = RegleValidation.objects.all()
    serializer_class = RegleSerializer
    permission_classes = [PublicReadBackOfficeWrite]
    pagination_class = None
    filterset_fields = ["filiere"]


def simulate(ues, notes, cible=None):
    """
    Simulateur indicatif. `notes` = {ecue_id: note/20}. Pour chaque UE :
    moyenne pondérée par les coefficients ECUE, validation si >= seuil
    (et aucune ECUE sous la note éliminatoire si définie).
    """
    out, credits_acquis, credits_total = [], 0, 0
    for ue in ues:
        ecues = list(ue.ecues.all())
        total_coef = sum((e.coefficient for e in ecues), Decimal(0))
        saisies = [(e, notes.get(str(e.id))) for e in ecues]
        manquantes = [e for e, n in saisies if n is None]
        somme = sum((Decimal(str(n)) * e.coefficient for e, n in saisies if n is not None), Decimal(0))
        coef_saisi = sum((e.coefficient for e, n in saisies if n is not None), Decimal(0))
        moyenne = (somme / coef_saisi) if coef_saisi else None
        eliminee = bool(ue.note_eliminatoire is not None and any(n is not None and Decimal(str(n)) < ue.note_eliminatoire for _, n in saisies))
        valide = bool(moyenne is not None and not manquantes and moyenne >= ue.seuil_validation and not eliminee)
        besoin = None
        if cible is not None and manquantes and total_coef:
            # Note moyenne nécessaire sur les ECUE restantes pour atteindre la cible de l'UE
            restant = total_coef - coef_saisi
            if restant:
                besoin = float(max(Decimal(0), (Decimal(str(cible)) * total_coef - somme) / restant))
        credits_total += ue.credits
        if valide:
            credits_acquis += ue.credits
        out.append({
            "ue": ue.id, "code": ue.code, "intitule": ue.intitule, "credits": ue.credits,
            "moyenne": round(float(moyenne), 2) if moyenne is not None else None,
            "valide": valide, "eliminee": eliminee, "incomplete": bool(manquantes),
            "note_necessaire": round(besoin, 2) if besoin is not None else None,
        })
    return {"ues": out, "credits_acquis": credits_acquis, "credits_total": credits_total,
            "avertissement": "Simulation indicative : seules les décisions du jury font foi."}


class SimulateurView(viewsets.ViewSet):
    permission_classes = [permissions.IsAuthenticated]

    @action(detail=False, methods=["post"], url_path="simulate")
    def simulate(self, request):
        ue_ids = request.data.get("ues", [])
        notes = {str(k): v for k, v in (request.data.get("notes") or {}).items() if v not in (None, "")}
        ues = UE.objects.filter(id__in=ue_ids).prefetch_related("ecues")
        return Response(simulate(ues, notes, request.data.get("cible")))

    @action(detail=False, methods=["get"], url_path="stats")
    def stats(self, request):
        return Response({
            "filieres": Filiere.objects.count(), "ues": UE.objects.count(), "ecues": ECUE.objects.count(),
            "classes": Classe.objects.count(),
            "par_niveau": list(UE.objects.values("niveau").annotate(n=Count("id")).order_by("niveau")),
        })
