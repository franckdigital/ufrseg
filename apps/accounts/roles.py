"""Rôles, hiérarchie de gestion des comptes et matrice des permissions (affichée dans le dashboard)."""
import secrets
import string

ROLES = {
    "ADMIN": ("Administrateur général", "Accès total : comptes, paramètres, finances, contenus."),
    "DECANAT": ("Décanat", "Pilotage académique et financier de l'UFR."),
    "SCOLARITE": ("Scolarité", "Gestion des étudiants, dossiers, demandes et notes."),
    "ENSEIGNANT": ("Enseignant", "Cours, TD, évaluations et notes de ses classes."),
    "ETUDIANT": ("Étudiant", "Espace personnel : bibliothèque, classe, démarches."),
}

# Qui peut créer / modifier / désactiver quels rôles
MANAGE = {
    "ADMIN": {"ADMIN", "DECANAT", "SCOLARITE", "ENSEIGNANT", "ETUDIANT"},
    "DECANAT": {"SCOLARITE", "ENSEIGNANT", "ETUDIANT"},
    "SCOLARITE": {"ETUDIANT"},
}

_ALL = ["ADMIN", "DECANAT", "SCOLARITE", "ENSEIGNANT", "ETUDIANT"]
_BACK = ["ADMIN", "DECANAT", "SCOLARITE"]
_STAFF = ["ADMIN", "DECANAT", "SCOLARITE", "ENSEIGNANT"]

# (groupe, fonctionnalité, rôles autorisés)
FEATURES = [
    ("Comptes", "Créer / modifier tous les rôles (y compris administrateurs)", ["ADMIN"]),
    ("Comptes", "Créer / modifier scolarité, enseignants et étudiants", ["ADMIN", "DECANAT"]),
    ("Comptes", "Créer / modifier des étudiants", _BACK),
    ("Comptes", "Consulter la liste des étudiants (saisie des notes)", _STAFF),
    ("Bibliothèque", "Consulter les documents (sans abonnement)", _STAFF),
    ("Bibliothèque", "Consulter les documents (avec abonnement)", ["ETUDIANT"]),
    ("Bibliothèque", "Publier un document directement", _BACK),
    ("Bibliothèque", "Proposer un document (profil auteur, rémunéré)", ["ENSEIGNANT", "ETUDIANT"]),
    ("Bibliothèque", "Valider, rejeter, suspendre un document", _BACK),
    ("Enseignement", "Créer des TD et des évaluations", _STAFF),
    ("Enseignement", "Saisir et publier les notes", _STAFF),
    ("Enseignement", "Passer des évaluations, déposer des TD", ["ETUDIANT"]),
    ("Enseignement", "Gérer filières, classes, UE, ECUE, règles de validation", _BACK),
    ("Administration", "Traiter les demandes, dossiers et rendez-vous", _BACK),
    ("Administration", "Étudier les candidatures Master / Doctorat", _BACK),
    ("Administration", "Publier annonces, calendrier, FAQ, offres", _BACK),
    ("Administration", "Faire des demandes (relevés, attestations…) et candidater", ["ETUDIANT"]),
    ("Finances", "Tarifs, répartition des revenus, reversements aux auteurs", ["ADMIN", "DECANAT"]),
    ("Finances", "Souscrire un abonnement", ["ETUDIANT"]),
]


def can_manage(actor_role: str, target_role: str) -> bool:
    return target_role in MANAGE.get(actor_role, set())


def generate_secret(role: str) -> str:
    """Étudiant : PIN à 4 chiffres (non trivial). Autres rôles : mot de passe de 10 caractères."""
    if role == "ETUDIANT":
        while True:
            pin = "".join(secrets.choice(string.digits) for _ in range(4))
            if len(set(pin)) > 1 and pin not in ("1234", "4321", "0123"):
                return pin
    alphabet = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(10))
