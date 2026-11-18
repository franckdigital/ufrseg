from datetime import date, timedelta

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.academics.models import ECUE, UE, AnneeAcademique, Classe, Filiere, Parcours, RegleValidation
from apps.accounts.models import User
from apps.billing.models import Plan, RemunerationRule, RevenueSplit
from apps.communication.models import FAQ, Annonce, Evenement, Offre
from apps.library.models import Document

PDF = b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj 2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj 3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF"


class Command(BaseCommand):
    help = "Crée des données de démonstration (idempotent)."

    def handle(self, *a, **kw):
        today = timezone.localdate()
        annee, _ = AnneeAcademique.objects.get_or_create(
            libelle="2025-2026", defaults=dict(debut=date(2025, 10, 1), fin=date(2026, 7, 31), active=True))

        def user(phone, first, last, role, pw, **extra):
            u = User.objects.filter(phone="+225" + phone).first()
            if not u:
                u = User.objects.create_user(phone, pw, first_name=first, last_name=last, role=role, **extra)
            return u

        user("0700000000", "Admin", "UFR", "ADMIN", "admin1234", is_staff=True, is_superuser=True)
        doyen = user("0700000001", "Marie", "KONAN", "DECANAT", "decanat1234", is_staff=True)
        user("0700000002", "Awa", "TRAORÉ", "SCOLARITE", "scol1234", is_staff=True)
        prof = user("0700000003", "Koffi", "YAO", "ENSEIGNANT", "prof1234")
        prof2 = user("0700000004", "Aminata", "BAMBA", "ENSEIGNANT", "prof1234")

        data = {
            "ECO": ("Sciences Économiques", ["Économie du développement", "Économie monétaire et bancaire", "Mathématiques et Statistiques appliquées à l'Économie"]),
            "GES": ("Sciences de Gestion", ["Finance-Comptabilité", "Marketing", "Ressources humaines"]),
        }
        filieres = {}
        for code, (nom, parcours) in data.items():
            f, _ = Filiere.objects.get_or_create(code=code, defaults=dict(
                nom=nom, description=f"Formation en {nom.lower()} de l'UFR SEG de l'UFHB.",
                debouches="Banques, assurances, cabinets conseil, administrations, organisations internationales, entrepreneuriat.",
                conditions_admission="Baccalauréat série A, B, C, D ou équivalent ; orientation validée par la DOB."))
            filieres[code] = f
            for p in parcours:
                Parcours.objects.get_or_create(filiere=f, nom=p)

        c_eco, _ = Classe.objects.get_or_create(nom="Licence 1 Économie", annee=annee, defaults=dict(filiere=filieres["ECO"], niveau="L1"))
        Classe.objects.get_or_create(nom="Licence 2 Gestion", annee=annee, defaults=dict(filiere=filieres["GES"], niveau="L2"))
        user("0707070707", "Kouadio", "N'GUESSAN", "ETUDIANT", "1234", matricule="21SEG0001", classe=c_eco, has_pin=True)
        auteur = user("0708080808", "Fatou", "DIALLO", "ETUDIANT", "1234", matricule="20SEG0042", classe=c_eco, has_pin=True, is_author=True)

        catalogue = [
            ("ECO", "L1", 1, "ECO101", "Microéconomie 1", [("ECO101A", "Théorie du consommateur", 2, prof), ("ECO101B", "Théorie du producteur", 2, prof)]),
            ("ECO", "L1", 1, "ECO102", "Macroéconomie 1", [("ECO102A", "Comptabilité nationale", 1, prof2), ("ECO102B", "Équilibre macroéconomique", 2, prof2)]),
            ("ECO", "L1", 1, "MAT101", "Mathématiques pour économistes", [("MAT101A", "Analyse", 2, prof2), ("MAT101B", "Algèbre linéaire", 1, prof2)]),
            ("ECO", "L1", 2, "ECO201", "Statistique descriptive", [("ECO201A", "Statistique univariée", 1, prof), ("ECO201B", "Statistique bivariée", 1, prof)]),
            ("GES", "L2", 3, "GES301", "Comptabilité générale", [("GES301A", "Opérations courantes", 2, prof2), ("GES301B", "Opérations de fin d'exercice", 2, prof2)]),
        ]
        ecues = []
        for fcode, niv, sem, code, intitule, items in catalogue:
            ue, _ = UE.objects.get_or_create(code=code, filiere=filieres[fcode], defaults=dict(intitule=intitule, niveau=niv, semestre=sem, credits=6, coefficient=3))
            for ec, it, coef, ens in items:
                e, _ = ECUE.objects.get_or_create(ue=ue, code=ec, defaults=dict(intitule=it, coefficient=coef, enseignant=ens, volume_horaire=30, modalites="CC 40% + Examen 60%"))
                ecues.append(e)

        for i, (t, c) in enumerate([
            ("Validation d'une ECUE", "Une ECUE est validée lorsque la moyenne pondérée (CC 40 % + examen 60 %) est supérieure ou égale à 10/20."),
            ("Validation d'une UE", "Une UE est validée lorsque la moyenne de ses ECUE, pondérée par les coefficients, atteint 10/20. Les crédits sont alors acquis dans leur totalité."),
            ("Compensation", "La compensation s'opère entre les ECUE d'une même UE puis entre les UE d'un même semestre, sauf note éliminatoire."),
            ("Passage en année supérieure", "Le passage est prononcé par le jury lorsque l'étudiant a acquis au moins 45 crédits sur 60 et validé les UE fondamentales."),
        ]):
            RegleValidation.objects.get_or_create(titre=t, defaults=dict(contenu=c, ordre=i))

        prix = {"ESSENTIEL": {1: 1000, 3: 2500, 6: 4500, 12: 8000}, "PREMIUM": {1: 2000, 3: 5000, 6: 9000, 12: 15000}}
        for pack, grid in prix.items():
            for mois, p in grid.items():
                Plan.objects.update_or_create(pack=pack, mois=mois, defaults=dict(prix=p, actif=True))
        if not RevenueSplit.objects.exists():
            RevenueSplit.objects.create(decanat=40, auteurs=40, plateforme=20)
        for cat, v, d in [("MEMOIRE", 3, 8), ("DEVOIR", 2, 5), ("TD", 2, 5), ("EXAMEN", 2, 5), ("CORRECTION", 3, 8), ("SUPPORT", 2, 4)]:
            RemunerationRule.objects.get_or_create(categorie=cat, defaults=dict(par_consultation=v, par_telechargement=d))

        docs = [
            ("Sujet d'examen Microéconomie 1 — Session 1", "EXAMEN", ecues[0], None),
            ("Corrigé Microéconomie 1 — Session 1", "CORRECTION", ecues[0], "Sujet d'examen Microéconomie 1 — Session 1"),
            ("TD n°3 Macroéconomie : comptabilité nationale", "TD", ecues[2], None),
            ("Polycopié Analyse — Licence 1", "SUPPORT", ecues[4], None),
            ("Mémoire : Inclusion financière et PME en Côte d'Ivoire", "MEMOIRE", None, None),
            ("Devoir surveillé Statistique univariée", "DEVOIR", ecues[6], None),
        ]
        for titre, cat, ec, lie in docs:
            if Document.objects.filter(titre=titre).exists():
                continue
            d = Document(titre=titre, categorie=cat, description="Document de démonstration.", filiere=filieres["ECO"], niveau="L1", annee=annee,
                         ue=ec.ue if ec else None, ecue=ec, auteur=auteur, statut="PUBLIE", published_at=timezone.now(),
                         document_lie=Document.objects.filter(titre=lie).first() if lie else None)
            d.fichier.save("demo.pdf", ContentFile(PDF), save=False)
            d.taille = len(PDF)
            d.save()

        if not Annonce.objects.exists():
            Annonce.objects.create(titre="Rentrée académique 2025-2026", categorie="RENTREE", resume="Les inscriptions administratives sont ouvertes.", contenu="Les inscriptions administratives et pédagogiques sont ouvertes du 1er octobre au 15 novembre. Rendez-vous au service de scolarité ou en ligne.", epingle=True, auteur=doyen)
            Annonce.objects.create(titre="Calendrier des examens du premier semestre", categorie="EXAMENS", resume="Consultez les dates dans le calendrier académique.", contenu="Les examens du semestre 1 se dérouleront du 12 au 30 janvier. Les convocations sont disponibles sur la plateforme.", auteur=doyen)
            Annonce.objects.create(titre="Appel à candidatures — bourses d'excellence", categorie="BOURSE", resume="Dépôt des dossiers avant le 30 novembre.", contenu="Les étudiants de Master peuvent déposer leur dossier de bourse d'excellence auprès du décanat.", auteur=doyen)
        if not Evenement.objects.exists():
            now = timezone.now()
            for t, ty, d in [("Rentrée solennelle", "RENTREE", 5), ("Devoirs surveillés S1", "DEVOIR", 40), ("Examens S1", "EXAMEN", 75), ("Date limite dépôt mémoires", "DEPOT", 90), ("Soutenances Master", "SOUTENANCE", 120)]:
                Evenement.objects.create(titre=t, type=ty, debut=now + timedelta(days=d), lieu="UFR SEG — Cocody")
        if not FAQ.objects.exists():
            for cat, q, r in [
                ("Inscriptions", "Comment m'inscrire à l'UFR SEG ?", "Les nouveaux bacheliers sont orientés par la DOB puis finalisent leur inscription administrative auprès du service de scolarité. Les réinscriptions se font en ligne depuis votre espace étudiant."),
                ("Bibliothèque", "Quels sont les tarifs d'abonnement à la bibliothèque numérique ?", "Pack Essentiel : 1 000 FCFA/mois (8 000 FCFA/an). Pack Premium avec corrections : 2 000 FCFA/mois (15 000 FCFA/an). Paiement par Orange Money, MTN, Moov, Wave ou carte."),
                ("Bibliothèque", "Quelle différence entre Essentiel et Premium ?", "Le Pack Essentiel donne accès à tous les documents sans correction. Le Pack Premium donne en plus accès aux corrigés, barèmes et solutions détaillées."),
                ("Scolarité", "Comment obtenir une attestation de scolarité ?", "Faites la demande depuis votre espace étudiant, rubrique Démarches. Le document est délivré après validation de la scolarité."),
                ("Examens", "Comment valider une UE ?", "Une UE est validée avec une moyenne pondérée d'au moins 10/20. Utilisez le simulateur de la plateforme pour estimer vos résultats ; seul le jury décide officiellement."),
                ("Réintégration", "Comment demander une réintégration ?", "Déposez votre demande avec les justificatifs depuis l'espace Démarches > Réintégration. Votre dossier est vérifié puis transmis au décanat."),
                ("Auteurs", "Comment gagner de l'argent avec mes documents ?", "Activez le profil auteur, déposez vos TD, sujets et corrections. Après validation par le décanat, vous êtes rémunéré pour chaque consultation et téléchargement qualifié."),
            ]:
                FAQ.objects.create(categorie=cat, question=q, reponse=r)
        if not Offre.objects.exists():
            Offre.objects.create(titre="Stagiaire analyste financier", type="STAGE", organisation="Banque partenaire", lieu="Abidjan-Plateau", description="Stage de 6 mois, Master 1 Finance.", date_limite=today + timedelta(days=45))

        from django.core.management import call_command
        call_command("seed_admissions")
        self.stdout.write(self.style.SUCCESS("Données de démonstration prêtes."))
        self.stdout.write("Comptes (téléphone / secret) : Admin 0700000000 / admin1234 ; Décanat 0700000001 / decanat1234 ; Scolarité 0700000002 / scol1234 ; Enseignant 0700000003 / prof1234 ; Étudiant 0707070707 / PIN 1234 ; Auteur 0708080808 / PIN 1234")
