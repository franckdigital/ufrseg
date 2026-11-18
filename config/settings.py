import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "dev-insecure-key-change-me")
DEBUG = os.getenv("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = os.getenv("DJANGO_ALLOWED_HOSTS", "*").split(",")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "corsheaders",
    "django_filters",
    "drf_spectacular",
    "apps.accounts",
    "apps.academics",
    "apps.library",
    "apps.billing",
    "apps.learning",
    "apps.services",
    "apps.communication",
    "apps.admissions",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    }
]
WSGI_APPLICATION = "config.wsgi.application"

# Base de données — au choix :
#   1) variables séparées : DB_ENGINE (postgresql|mysql), DB_NAME, DB_USER, DB_PASSWORD, DB_HOST, DB_PORT   (recommandé)
#   2) une URL : DATABASE_URL=postgres://user:pass@host:5432/base   (un « @ » dans le mot de passe s'écrit %40)
#   3) rien : SQLite locale (développement)
_db_url = os.getenv("DATABASE_URL", "")
if os.getenv("DB_NAME"):
    _engine = os.getenv("DB_ENGINE", "mysql").lower()
    _mysql = _engine.startswith("mysql")
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.mysql" if _mysql else "django.db.backends.postgresql",
            "NAME": os.getenv("DB_NAME"),
            "USER": os.getenv("DB_USER", ""),
            "PASSWORD": os.getenv("DB_PASSWORD", ""),
            "HOST": os.getenv("DB_HOST", "127.0.0.1"),
            "PORT": os.getenv("DB_PORT", "3306" if _mysql else "5432"),
            **({"OPTIONS": {"charset": "utf8mb4"}} if _mysql else {}),
        }
    }
elif _db_url.startswith(("postgres", "mysql")):
    from urllib.parse import unquote, urlparse

    u = urlparse(_db_url)
    _mysql = u.scheme.startswith("mysql")
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.mysql" if _mysql else "django.db.backends.postgresql",
            "NAME": u.path.lstrip("/"),
            "USER": unquote(u.username or ""),
            "PASSWORD": unquote(u.password or ""),
            "HOST": u.hostname,
            "PORT": u.port or (3306 if _mysql else 5432),
            **({"OPTIONS": {"charset": "utf8mb4"}} if _mysql else {}),
        }
    }
else:
    DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}}

# Garde-fou : en production, jamais de SQLite silencieuse (ex. .env illisible par l'utilisateur du service).
if not DEBUG and DATABASES["default"]["ENGINE"].endswith("sqlite3"):
    raise RuntimeError("Base de données non configurée : renseignez DB_ENGINE/DB_NAME/DB_USER/DB_PASSWORD dans backend/.env "
                       "(le fichier doit être lisible par l'utilisateur du service, ex. chown root:www-data + chmod 640).")

AUTH_USER_MODEL = "accounts.User"
# Les PIN à 4 chiffres sont autorisés : pas de validateurs de complexité côté API.
AUTH_PASSWORD_VALIDATORS = []

LANGUAGE_CODE = "fr-fr"
TIME_ZONE = "Africa/Abidjan"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = Path(os.getenv("STATIC_ROOT", BASE_DIR / "staticfiles"))
MEDIA_URL = "media/"
MEDIA_ROOT = Path(os.getenv("MEDIA_ROOT", BASE_DIR / "media"))
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework_simplejwt.authentication.JWTAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_THROTTLE_CLASSES": ["rest_framework.throttling.ScopedRateThrottle"],
    "DEFAULT_THROTTLE_RATES": {"auth": "20/min", "assistant": "30/min"},
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(hours=2),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=30),
    "ROTATE_REFRESH_TOKENS": True,
}

SPECTACULAR_SETTINGS = {
    "TITLE": "API UFR SEG — UFHB",
    "DESCRIPTION": "Plateforme numérique de l'UFR des Sciences Économiques et de Gestion",
    "VERSION": "1.0.0",
}

CORS_ALLOWED_ORIGINS = [o for o in os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:5173,http://localhost:5174").split(",") if o]
CORS_ALLOW_ALL_ORIGINS = DEBUG

# --- Production (derrière nginx + HTTPS) ---
# Nginx sert les fichiers privés via X-Accel-Redirect (emplacement interne /_protected/)
USE_X_ACCEL = os.getenv("USE_X_ACCEL", "0") == "1"
CSRF_TRUSTED_ORIGINS = [o for o in os.getenv("CSRF_TRUSTED_ORIGINS", "").split(",") if o]
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = False  # la redirection HTTP→HTTPS est faite par nginx
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_CONTENT_TYPE_NOSNIFF = True
    if SECRET_KEY.startswith("dev-insecure"):
        raise RuntimeError("DJANGO_SECRET_KEY doit être défini en production.")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-haiku-5-5")

# Clé de répartition par défaut des recettes (configurable via admin : billing.RevenueSplit)
DEFAULT_REVENUE_SPLIT = {"decanat": 40, "auteurs": 40, "plateforme": 20}

# --- CinetPay (API v1 « Aurora ») : SANDBOX par défaut ---
# Sans identifiants valides, le mode simulation (CINETPAY_MOCK) est actif en DEBUG et le paiement se confirme via le bouton de test.
CINETPAY_API_KEY = os.getenv("CINETPAY_API_KEY", "")
CINETPAY_API_PASSWORD = os.getenv("CINETPAY_API_PASSWORD", "")
CINETPAY_SITE_ID = os.getenv("CINETPAY_SITE_ID", "")
CINETPAY_ALLOW_LIVE = os.getenv("CINETPAY_ALLOW_LIVE", "0") == "1"
CINETPAY_MOCK = os.getenv("CINETPAY_MOCK", "" if (CINETPAY_API_KEY and CINETPAY_API_PASSWORD) else "1").lower() in ("1", "true")
# URL publique de l'API (notify_url CinetPay) et du dashboard (retour de paiement)
BACKEND_BASE_URL = os.getenv("BACKEND_BASE_URL", "http://127.0.0.1:8010")
PUBLIC_WEB_URL = os.getenv("PUBLIC_WEB_URL", "http://localhost:5174")
