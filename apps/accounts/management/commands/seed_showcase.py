"""Données de DÉMONSTRATION pour visiter la plateforme : un enseignant, un étudiant, des documents, un TD, une évaluation…

    python manage.py seed_showcase            # crée (idempotent)
    python manage.py seed_showcase --purge    # supprime tout ce que cette commande a créé

Les comptes de démo ont des identifiants connus : à supprimer (--purge) avant l'ouverture au public.
"""
from datetime import timedelta

from django.core.files.base import ContentFile
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.academics.models import ECUE, UE, AnneeAcademique, Classe, Filiere
from apps.accounts.models import User
from apps.billing.models import Plan, Subscription
from apps.communication.models import FAQ, Annonce, Evenement
from apps.learning.models import Devoir, Evaluation, Note, Question
from apps.library.models import Document

TEACHER = dict(phone="0701010101", first_name="Koffi", last_name="YAO", pw="enseignant2026")
STUDENT = dict(phone="0702020202", first_name="Aya", last_name="KOUASSI", pw="1234")
MARK = "[DÉMO]"


def make_pdf(title, lines):
    """PDF d'une page, sans dépendance (police Helvetica, accents WinAnsi)."""
    def esc(s):
        return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    ops = ["BT /F1 20 Tf 50 790 Td ({}) Tj ET".format(esc(title))]
    y = 750
    for ln in lines:
        ops.append("BT /F1 12 Tf 50 {} Td ({}) Tj ET".format(y, esc(ln)))
        y -= 20
    stream = "\n".join(ops).encode("cp1252", "replace")
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
    ]
    out, offs = b"%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offs.append(len(out))
        out += b"%d 0 obj\n" % i + o + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offs)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF" % (len(objs) + 1, xref)
    return out


class Command(BaseCommand):
    help = "Données de démonstration (enseignant, étudiant, documents, TD, évaluation)."

    def add_arguments(self, p):
        p.add_argument("--purge", action="store_true", help="Supprime les données créées par cette commande")

    def handle(self, *a, **o):
        if o["purge"]:
            return self.purge()
        call_command("init_production")  # filières, année, formules, programmes (idempotent)
        now = timezone.now()
        annee = AnneeAcademique.objects.filter(active=True).first() or AnneeAcademique.objects.first()
        eco = Filiere.objects.get(code="ECO")

        def user(d, **extra):
            u = User.objects.filter(phone="+225" + d["phone"]).first()
            if not u:
                u = User.objects.create_user(d["phone"], d["pw"], first_name=d["first_name"], last_name=d["last_name"], **extra)
            return u

        prof = user(TEACHER, role="ENSEIGNANT")
        classe, _ = Classe.objects.get_or_create(nom="Licence 1 Économie", annee=annee, defaults=dict(filiere=eco, niveau="L1"))
        etu = user(STUDENT, role="ETUDIANT", matricule="25SEG0101", classe=classe, has_pin=True, is_author=True)
        if etu.classe_id != classe.id:
            etu.classe = classe
            etu.save(update_fields=["classe"])

        # Abonnement Premium de 30 jours pour que l'étudiant voie tous les documents (corrigés compris)
        if not Subscription.objects.filter(user=etu, annule=False, fin__gt=now).exists():
            Subscription.objects.create(user=etu, plan=Plan.objects.get(pack="PREMIUM", mois=1), debut=now, fin=now + timedelta(days=30))

        # UE / ECUE (rattachées à l'enseignant)
        cat = [
            ("ECO101", "Microéconomie 1", [("ECO101A", "Théorie du consommateur", 2), ("ECO101B", "Théorie du producteur", 2)]),
            ("ECO102", "Macroéconomie 1", [("ECO102A", "Comptabilité nationale", 1), ("ECO102B", "Équilibre macroéconomique", 2)]),
            ("MAT101", "Mathématiques pour économistes", [("MAT101A", "Analyse", 2), ("MAT101B", "Algèbre linéaire", 1)]),
        ]
        ecues = {}
        for code, nom, items in cat:
            ue, _ = UE.objects.get_or_create(code=code, filiere=eco, defaults=dict(intitule=nom, niveau="L1", semestre=1, credits=6, coefficient=3))
            for ec, it, coef in items:
                e, _ = ECUE.objects.get_or_create(ue=ue, code=ec, defaults=dict(intitule=it, coefficient=coef, volume_horaire=30, modalites="CC 40% + Examen 60%"))
                if e.enseignant_id != prof.id:
                    e.enseignant = prof
                    e.save(update_fields=["enseignant"])
                ecues[ec] = e

        # ── Documents publiés (PDF réels, lisibles) ──
        docs = [
            ("Sujet d'examen — Théorie du consommateur (S1)", "EXAMEN", "ECO101A", None, ["Exercice 1 : Fonction d'utilité et contrainte budgétaire.", "Exercice 2 : Équilibre du consommateur (Cobb-Douglas).", "Exercice 3 : Effet de substitution et effet revenu.", "Durée : 2 h. Calculatrice autorisée."]),
            ("Corrigé — Théorie du consommateur (S1)", "CORRECTION", "ECO101A", "Sujet d'examen — Théorie du consommateur (S1)", ["Corrigé détaillé et barème.", "Exercice 1 : U = x^a y^(1-a) ... (3 pts)", "Exercice 2 : x* = aR/Px ; y* = (1-a)R/Py (4 pts)", "Exercice 3 : décomposition de Slutsky (3 pts)"]),
            ("TD n°3 — Comptabilité nationale", "TD", "ECO102A", None, ["Calculer le PIB par les trois approches.", "Distinguer PIB nominal et PIB réel.", "Construire le tableau économique d'ensemble simplifié."]),
            ("Corrigé du TD n°3 — Comptabilité nationale", "CORRECTION", "ECO102A", "TD n°3 — Comptabilité nationale", ["PIB (production) = somme des valeurs ajoutées + impôts - subventions.", "PIB réel = PIB nominal / indice des prix x 100."]),
            ("Polycopié — Analyse (L1)", "SUPPORT", "MAT101A", None, ["Chapitre 1 : Suites numériques.", "Chapitre 2 : Limites et continuité.", "Chapitre 3 : Dérivation et applications économiques."]),
            ("Fiche de révision — Équilibre macroéconomique", "SUPPORT", "ECO102B", None, ["Modèle IS-LM : courbes, déplacements, politiques budgétaire et monétaire.", "Multiplicateur keynésien : k = 1 / (1 - c)."]),
            ("Devoir surveillé — Algèbre linéaire", "DEVOIR", "MAT101B", None, ["Exercice 1 : Résolution d'un système par le pivot de Gauss.", "Exercice 2 : Déterminant et inverse d'une matrice 3x3."]),
            ("Mémoire — Inclusion financière et PME en Côte d'Ivoire", "MEMOIRE", None, None, ["Résumé : étude de l'accès au financement des PME ivoiriennes.", "Méthodologie : enquête auprès de 120 entreprises.", "Résultats : le crédit de proximité améliore la croissance des PME."]),
        ]
        by_title = {}
        for titre, cat_, ec, lie, lines in docs:
            full = f"{MARK} {titre}"
            d = Document.objects.filter(titre=full).first()
            if not d:
                e = ecues.get(ec) if ec else None
                d = Document(titre=full, categorie=cat_, description=f"{MARK} Document de démonstration.", filiere=eco, niveau="L1", annee=annee,
                             ue=e.ue if e else None, ecue=e, auteur=prof, statut="PUBLIE", published_at=now,
                             document_lie=by_title.get(lie))
                pdf = make_pdf(titre, lines)
                d.fichier.save("demo.pdf", ContentFile(pdf), save=False)
                d.taille = len(pdf)
                d.save()
            by_title[titre] = d

        # Document soumis par l'étudiant auteur : apparaît dans « À valider » côté décanat
        pend = f"{MARK} TD corrigé — Théorie du producteur (proposé par un étudiant)"
        if not Document.objects.filter(titre=pend).exists():
            pdf = make_pdf("TD corrigé — Théorie du producteur", ["Document proposé par un étudiant, en attente de validation."])
            d = Document(titre=pend, categorie="TD", description=f"{MARK} En attente de validation.", filiere=eco, niveau="L1", annee=annee,
                         ue=ecues["ECO101B"].ue, ecue=ecues["ECO101B"], auteur=etu, statut="SOUMIS")
            d.fichier.save("demo.pdf", ContentFile(pdf), save=False)
            d.taille = len(pdf)
            d.save()

        # ── TD et évaluation en ligne ──
        if not Devoir.objects.filter(titre__startswith=MARK).exists():
            Devoir.objects.create(classe=classe, ecue=ecues["ECO101A"], titre=f"{MARK} TD n°4 — Équilibre du consommateur", cree_par=prof, date_limite=now + timedelta(days=10),
                                  enonce="Un consommateur dispose d'un revenu R = 100 et consomme deux biens (prix 2 et 5). Déterminez son panier optimal pour U = x^0,5 y^0,5.")
        if not Evaluation.objects.filter(titre__startswith=MARK).exists():
            ev = Evaluation.objects.create(classe=classe, ecue=ecues["ECO101A"], titre=f"{MARK} Quiz de révision — Microéconomie", type="TRAIN", cree_par=prof, publie=True,
                                           duree_min=20, debut=now - timedelta(days=1), fin=now + timedelta(days=30), tentatives_max=3, resultats_publies=True,
                                           consignes="Quiz d'entraînement : 5 questions, correction automatique. Le changement d'onglet est enregistré.")
            Question.objects.create(evaluation=ev, type="QCM", enonce="Quelle est la pente de la contrainte budgétaire ?", options=["Px/Py", "-Px/Py", "R/Px", "Py/Px"], reponse=1, bareme=2, ordre=0)
            Question.objects.create(evaluation=ev, type="VF", enonce="Un bien normal voit sa demande augmenter quand le revenu augmente.", reponse=True, bareme=1, ordre=1)
            Question.objects.create(evaluation=ev, type="MULTI", enonce="Quels sont les effets d'une hausse du prix d'un bien ?", options=["Effet de substitution", "Effet de report", "Effet revenu", "Effet de seuil"], reponse=[0, 2], bareme=2, ordre=2)
            Question.objects.create(evaluation=ev, type="NUM", enonce="Avec U = x^0,5 y^0,5, R = 100 et Px = 2, quelle quantité x* est consommée ?", reponse={"valeur": 25, "tolerance": 0.1}, bareme=2, ordre=3)
            Question.objects.create(evaluation=ev, type="OUVERTE", enonce="Expliquez en quelques lignes la différence entre effet de substitution et effet revenu.", bareme=3, ordre=4)

        # ── Notes publiées de l'étudiant ──
        for ec, typ, val in [("ECO101A", "CC", 13), ("ECO101A", "EXAMEN", 11.5), ("ECO102A", "CC", 9), ("MAT101A", "CC", 14.25)]:
            Note.objects.get_or_create(etudiant=etu, ecue=ecues[ec], annee=annee, type=typ, defaults=dict(valeur=val, publiee=True, saisie_par=prof))

        # ── Communication (annonces, calendrier, FAQ) ──
        if not Annonce.objects.filter(titre__startswith=MARK).exists():
            Annonce.objects.create(titre=f"{MARK} Bienvenue sur la plateforme de l'UFR SEG", categorie="ADMIN", resume="Découvrez la bibliothèque, les TD et les évaluations en ligne.",
                                   contenu="Cette annonce est un exemple. Les étudiants reçoivent une notification à chaque publication.", epingle=True, auteur=prof)
        if not Evenement.objects.filter(titre__startswith=MARK).exists():
            for t, ty, d in [("Rentrée solennelle", "RENTREE", 7), ("Devoirs surveillés S1", "DEVOIR", 35), ("Examens du semestre 1", "EXAMEN", 70)]:
                Evenement.objects.create(titre=f"{MARK} {t}", type=ty, debut=now + timedelta(days=d), lieu="UFR SEG — Cocody")
        if not FAQ.objects.exists():
            FAQ.objects.create(categorie="Bibliothèque", question=f"{MARK} Comment accéder aux corrigés ?", reponse="Les corrigés sont inclus dans le Pack Premium.")

        self.stdout.write(self.style.SUCCESS("Démonstration prête."))
        self.stdout.write("Enseignant : 0701010101 / enseignant2026  — Étudiant : 0702020202 / PIN 1234 (abonnement Premium 30 jours)")
        self.stdout.write("Pour tout supprimer : python manage.py seed_showcase --purge")

    def purge(self):
        n = Document.objects.filter(titre__startswith=MARK).delete()[0]
        Devoir.objects.filter(titre__startswith=MARK).delete()
        Evaluation.objects.filter(titre__startswith=MARK).delete()
        Annonce.objects.filter(titre__startswith=MARK).delete()
        Evenement.objects.filter(titre__startswith=MARK).delete()
        FAQ.objects.filter(question__startswith=MARK).delete()
        for d in (STUDENT, TEACHER):
            User.objects.filter(phone="+225" + d["phone"]).delete()
        self.stdout.write(self.style.SUCCESS(f"Données de démonstration supprimées ({n} objets liés aux documents)."))
