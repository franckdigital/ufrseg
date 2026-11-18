from datetime import date

from django.core.management import call_command
from django.core.management.base import BaseCommand

from apps.academics.models import AnneeAcademique, Filiere, Parcours
from apps.billing.models import Plan, RemunerationRule, RevenueSplit


class Command(BaseCommand):
    help = "Données de base de PRODUCTION (sans comptes de démo) : formules, répartition, filières, guides, programmes. Idempotent."

    def handle(self, *a, **kw):
        AnneeAcademique.objects.get_or_create(libelle="2025-2026", defaults=dict(debut=date(2025, 10, 1), fin=date(2026, 7, 31), active=True))

        for code, nom, parcours in [
            ("ECO", "Sciences Économiques", ["Économie du développement", "Économie monétaire et bancaire", "Mathématiques et Statistiques appliquées à l'Économie"]),
            ("GES", "Sciences de Gestion", ["Finance-Comptabilité", "Marketing", "Ressources humaines"]),
        ]:
            f, _ = Filiere.objects.get_or_create(code=code, defaults=dict(nom=nom))
            for p in parcours:
                Parcours.objects.get_or_create(filiere=f, nom=p)

        # Tarifs indicatifs du cahier des charges — à valider par le décanat (modifiables dans le dashboard)
        prix = {"ESSENTIEL": {1: 1000, 3: 2500, 6: 4500, 12: 8000}, "PREMIUM": {1: 2000, 3: 5000, 6: 9000, 12: 15000}}
        for pack, grid in prix.items():
            for mois, p in grid.items():
                Plan.objects.get_or_create(pack=pack, mois=mois, defaults=dict(prix=p, actif=True))
        if not RevenueSplit.objects.exists():
            RevenueSplit.objects.create(decanat=40, auteurs=40, plateforme=20)
        for cat, v, d in [("MEMOIRE", 3, 8), ("DEVOIR", 2, 5), ("TD", 2, 5), ("EXAMEN", 2, 5), ("CORRECTION", 3, 8), ("SUPPORT", 2, 4)]:
            RemunerationRule.objects.get_or_create(categorie=cat, defaults=dict(par_consultation=v, par_telechargement=d))

        call_command("seed_admissions")
        self.stdout.write(self.style.SUCCESS("Données de base prêtes. Créez l'administrateur : python manage.py createsuperuser"))
