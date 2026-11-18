from datetime import date

from django.core.management.base import BaseCommand

from apps.academics.models import Filiere
from apps.admissions.models import Guide, Programme
from apps.services.models import FraisService

# Contenu INDICATIF : à relire et valider par le décanat (modifiable depuis le dashboard > Admissions).
GUIDES = [
    # ── Orientation des nouveaux bacheliers ──
    ("ORIENTATION", "compass", "Comment suis-je orienté(e) à l'UFR SEG ?", "Les nouveaux bacheliers sont orientés vers les filières selon leur série, leur moyenne et les capacités d'accueil.",
     "L'orientation des nouveaux bacheliers est prononcée au niveau national, en fonction de la série du baccalauréat, des résultats obtenus et des capacités d'accueil de chaque établissement.\n"
     "Étapes générales :\n- Consulter les résultats d'orientation publiés après le baccalauréat.\n- Vérifier votre affectation à l'UFR des Sciences Économiques et de Gestion (SEG).\n- Choisir ou confirmer votre filière lorsque plusieurs options vous sont ouvertes.\n- Poursuivre avec la pré-inscription puis l'inscription administrative."),
    ("ORIENTATION", "layers", "Les filières accessibles après le baccalauréat", "Sciences Économiques (dont Mathématiques et Statistiques appliquées à l'Économie) et Sciences de Gestion.",
     "L'UFR SEG propose en Licence 1 :\n- Sciences Économiques : économie générale, analyse économique, développement ; elle renferme le parcours Mathématiques et Statistiques appliquées à l'Économie (modélisation, statistique, économétrie).\n- Sciences de Gestion : comptabilité, finance, marketing, ressources humaines.\n"
     "Les séries A, B, C, D (ou équivalents) sont généralement concernées ; les conditions précises sont fixées chaque année. En Licence 1, le tronc commun permet de confirmer votre choix avant la spécialisation en Licence 2 et 3."),
    ("ORIENTATION", "help-circle", "Réorientation et changement de filière", "Possible sous conditions après la Licence 1.",
     "Un changement de filière ou de parcours peut être demandé en fin d'année, selon vos résultats et les places disponibles.\n- Faites la démarche « Changement de parcours » depuis votre espace.\n- Joignez vos relevés de notes et une lettre de motivation.\n- La décision est prise par le décanat après avis du responsable pédagogique."),
    # ── Inscription ──
    ("INSCRIPTION", "clipboard", "Le processus d'inscription pas à pas", "De la pré-inscription à la carte d'étudiant.",
     "1. Pré-inscription en ligne : renseignez vos informations personnelles et votre numéro de téléphone.\n"
     "2. Dépôt du dossier : acte de naissance, relevé de notes ou attestation du baccalauréat, photos d'identité, pièce d'identité.\n"
     "3. Paiement des droits d'inscription selon les modalités communiquées par l'université.\n"
     "4. Validation par le service de scolarité (vérification des pièces).\n"
     "5. Inscription pédagogique : choix des UE et rattachement à votre classe et groupe de TD.\n"
     "6. Retrait de la carte d'étudiant et accès à la plateforme."),
    ("INSCRIPTION", "file-text", "Pièces à fournir", "Liste type du dossier d'inscription.",
     "- Attestation ou relevé de notes du baccalauréat (original et copie).\n- Extrait d'acte de naissance.\n- Pièce d'identité.\n- 4 photos d'identité.\n- Justificatif de paiement des droits.\n- Pour les réinscriptions : relevé de notes de l'année précédente.\n- Pour les transferts : attestation de départ et relevés de l'établissement d'origine."),
    ("INSCRIPTION", "calendar", "Dates et réinscriptions", "Le calendrier est publié chaque année par le décanat.",
     "Les dates de pré-inscription, d'inscription administrative et de réinscription sont publiées dans la rubrique Actualités et le Calendrier académique.\nLes réinscriptions se font en ligne depuis l'espace étudiant (rubrique Démarches > Inscription / réinscription)."),
    # ── Parcours académique ──
    ("PARCOURS", "graduation-cap", "Licence (L1, L2, L3) — 3 ans", "6 semestres, 180 crédits : socle de connaissances puis spécialisation.",
     "- Licence 1 (S1-S2) : tronc commun, bases en économie, gestion, mathématiques, statistique et méthodologie.\n- Licence 2 (S3-S4) : approfondissement et début de spécialisation selon la filière.\n- Licence 3 (S5-S6) : spécialisation, stage ou mémoire de fin de cycle.\n"
     "Chaque semestre vaut 30 crédits. La licence est obtenue après validation des 180 crédits. À partir de la Licence 3, vous pouvez candidater en Master 1."),
    ("PARCOURS", "graduation-cap", "Master (M1, M2) — 2 ans", "4 semestres, 120 crédits : recherche ou professionnel/appliqué.",
     "- Master 1 (S7-S8) : enseignements de spécialité, méthodes quantitatives, initiation à la recherche ou stage.\n- Master 2 (S9-S10) : spécialisation, stage long et mémoire de fin d'études soutenu devant un jury.\n"
     "Deux orientations existent :\n- Master recherche : prépare à la thèse (méthodologie, séminaires, mémoire de recherche).\n- Master professionnel / appliqué : prépare à l'emploi (études de cas, stage, projets professionnels).\nL'admission en Master 1 est sélective (voir « Master 1 »)."),
    ("PARCOURS", "graduation-cap", "Doctorat — 3 ans et plus", "Thèse encadrée au sein d'une école doctorale.",
     "Le doctorat (bac+8) prépare aux métiers de la recherche et de l'enseignement supérieur, ainsi qu'à l'expertise de haut niveau.\n- Pré-requis : Master recherche (ou équivalent) avec un bon dossier académique.\n- Projet de thèse validé par un directeur de recherche.\n- 3 ans en moyenne, avec formations doctorales, publications et soutenance devant un jury."),
    # ── Master ──
    ("MASTER", "target", "Qui peut candidater en Master 1 ?", "À partir de la Licence 3 (en cours ou validée).",
     "Les étudiants de Licence 3 peuvent déposer leur candidature dès l'ouverture de la campagne, ainsi que les titulaires d'une licence ou d'un diplôme équivalent.\nLe nombre de places est limité pour chaque spécialité : l'admission est prononcée sur dossier, éventuellement après entretien."),
    ("MASTER", "list-checks", "Comment être sélectionné ? Les critères", "Dossier académique, cohérence du projet, éventuel entretien.",
     "Le jury examine en général :\n- Les moyennes de Licence 1, 2 et 3 (et la moyenne générale).\n- La régularité du parcours (absence ou faible nombre de redoublements).\n- Les notes dans les matières clés de la spécialité demandée.\n- La lettre de motivation et la cohérence du projet professionnel ou de recherche.\n- Le CV, les stages et expériences.\n- L'entretien, pour les candidats présélectionnés.\nLes pondérations exactes sont fixées par chaque spécialité."),
    ("MASTER", "route", "Le processus de sélection", "Six étapes, de la candidature à l'inscription.",
     "1. Choisissez votre spécialité et lisez ses critères.\n2. Remplissez le formulaire de candidature en ligne (moyennes, motivation, pièces).\n3. Réglez les frais de traitement du dossier par Mobile Money : votre dossier n'est soumis qu'après confirmation du paiement.\n4. Le jury étudie les dossiers.\n5. Les candidats présélectionnés sont convoqués à un entretien.\n6. Les résultats (admis, liste d'attente, non retenu) sont publiés et notifiés sur la plateforme ; les admis finalisent leur inscription.\nLes frais de dossier ne sont pas remboursables en cas de non-admission."),
    # ── Doctorat ──
    ("DOCTORAT", "microscope", "Comment est sélectionné un doctorant ?", "Sur dossier, projet de thèse et entretien.",
     "1. Obtenir un Master recherche (ou équivalent) avec une mention ou un bon dossier.\n2. Définir un sujet et prendre contact avec un directeur de thèse de l'UFR.\n3. Déposer la candidature (projet de recherche, CV, relevés, lettre du directeur envisagé) et régler les frais de dossier.\n4. Audition devant un comité de l'école doctorale.\n5. Inscription et signature de la charte du doctorat."),
    ("DOCTORAT", "book-open", "Master recherche ou Master appliqué ?", "Choisir selon votre objectif : thèse ou emploi.",
     "- Master recherche : recommandé si vous visez le doctorat, l'enseignement supérieur ou la recherche. Il comprend des séminaires de méthodologie et un mémoire de recherche.\n- Master professionnel / appliqué : recommandé si vous visez l'emploi (banque, entreprise, organisation internationale). Il comprend des études de cas et un stage.\nUn master appliqué peut permettre de s'orienter vers le doctorat sous conditions (passerelle, dossier de recherche solide)."),
]

PROGRAMMES = [
    # nom, filiere code, type, description, débouchés, critères, capacité
    ("Master Finance", "GES", "PRO", "Finance d'entreprise, de marché et bancaire : évaluation, gestion des risques, analyse financière.", "Analyste financier, chargé d'investissement, gestionnaire de risques, contrôleur de gestion, banques et assurances.", 40),
    ("Master Économie du développement", "ECO", "RECHERCHE", "Analyse des économies en développement, politiques publiques, pauvreté, croissance et institutions.", "Économiste dans les ministères et organisations internationales, chargé d'études, chercheur, ONG.", 35),
    ("Master Économie internationale", "ECO", "PRO", "Commerce international, finance internationale, intégration régionale, politiques commerciales.", "Chargé de commerce international, analyste de marchés, organisations régionales, douanes, banques.", 35),
    ("Master Économie agricole", "ECO", "PRO", "Économie rurale et agro-industrielle, filières agricoles, sécurité alimentaire, politiques agricoles.", "Chargé de projets agricoles, conseiller de filières, bailleurs de fonds, coopératives, administrations.", 30),
    ("Master Ressources humaines", "GES", "PRO", "Gestion des talents, droit social, paie, développement organisationnel et relations de travail.", "Responsable RH, chargé de recrutement, gestionnaire de paie, consultant en organisation.", 40),
    ("Master Marketing", "GES", "PRO", "Stratégie marketing, études de marché, marketing digital, comportement du consommateur, marque.", "Chef de produit, responsable marketing, chargé d'études, consultant, community / brand manager.", 40),
    ("Master Statistique et économétrie", "ECO", "RECHERCHE", "Modélisation statistique, économétrie appliquée, analyse de données et prévision.", "Statisticien, data analyst, économètre, instituts de statistique, banques centrales, recherche.", 30),
    ("Doctorat en Sciences Économiques et de Gestion", "ECO", "DOC", "Thèse de doctorat encadrée dans l'une des spécialités de l'UFR (économie, gestion, statistique).", "Enseignant-chercheur, chercheur, expert dans les institutions internationales, consultant senior.", 15),
]

CRITERES_M1 = ("Moyenne générale de Licence (L1 à L3) d'au moins 12/20, ou rang dans la promotion\nParcours régulier (pas plus d'un redoublement)\nNotes dans les matières clés de la spécialité\nLettre de motivation et projet professionnel cohérent\nCV, stages ou expériences en lien avec la spécialité\nEntretien pour les candidats présélectionnés")
CRITERES_DOC = ("Master recherche (ou équivalent) avec une moyenne d'au moins 14/20\nProjet de recherche clair et réalisable (problématique, méthode, état de l'art)\nAccord préalable d'un directeur de thèse\nPublications ou travaux de recherche appréciés\nAudition devant le comité de l'école doctorale")
PIECES_M1 = "Relevés de notes L1, L2 et L3\nAttestation de licence ou de scolarité en L3\nCurriculum vitae\nLettre de motivation (formulaire)\nPièce d'identité\nJustificatif de paiement des frais de dossier"
PIECES_DOC = "Diplôme de Master et relevés de notes\nProjet de recherche détaillé\nCurriculum vitae et liste des travaux\nLettre d'accord du directeur de thèse envisagé\nPièce d'identité\nJustificatif de paiement des frais de dossier"

FRAIS = {"RELEVE": 2000, "BULLETIN": 2000, "ATT_ADMISS": 3000}  # FCFA, indicatifs


class Command(BaseCommand):
    help = "Crée le contenu d'orientation/admission, les programmes Master/Doctorat et les frais de dossier (idempotent)."

    def handle(self, *a, **kw):
        for i, (cat, ico, titre, resume, contenu) in enumerate(GUIDES):
            Guide.objects.get_or_create(categorie=cat, titre=titre, defaults=dict(icone=ico, resume=resume, contenu=contenu, ordre=i))
        fil = {f.code: f for f in Filiere.objects.all()}
        for nom, code, typ, desc, deb, cap in PROGRAMMES:
            doc = typ == "DOC"
            Programme.objects.get_or_create(nom=nom, defaults=dict(
                niveau="DOC" if doc else "M1", type=typ, filiere=fil.get(code), description=desc, debouches=deb, capacite=cap,
                criteres=CRITERES_DOC if doc else CRITERES_M1, pieces=PIECES_DOC if doc else PIECES_M1,
                frais_dossier=20000 if doc else 10000, date_limite=date(2026, 9, 30)))
        for t, m in FRAIS.items():
            FraisService.objects.get_or_create(type=t, defaults={"montant": m})
        self.stdout.write(self.style.SUCCESS("Admissions : guides, programmes et frais prêts."))
