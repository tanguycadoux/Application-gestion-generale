"""Réglages du projet : application locale et mono-utilisateur, réglages non
durcis (voir docs/architecture.md, « Contexte »)."""

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Application locale, jamais exposée : clé et mode debug en dur.
SECRET_KEY = "django-insecure-#3%tazdi)001th(3sei&2rfwxnd)1jihx7zl96y&tdg&6r2iu0"

DEBUG = True

ALLOWED_HOSTS: list[str] = []


# Applications

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django_tailwind_cli",
    "core",
    "images",
    "note_taking",
    "todolist",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django_htmx.middleware.HtmxMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
ROOT_URLCONF = "app_gestion.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# `{{ form }}` rend les formulaires en grille, libellés à gauche (#132).
FORM_RENDERER = "core.forms.GridFormRenderer"

WSGI_APPLICATION = "app_gestion.wsgi.application"


# Base de données

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# Validation des mots de passe (comptes de l'admin)

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


# Langue et fuseau

LANGUAGE_CODE = "fr-fr"

TIME_ZONE = "Europe/Paris"

USE_I18N = True

USE_TZ = True


# Fichiers statiques

STATIC_URL = "static/"

STATICFILES_DIRS = [BASE_DIR / "static"]

# Tailwind CSS compilé par django-tailwind-cli (CLI autonome, sans Node) :
# `python manage.py tailwind build`, ou `tailwind runserver` pour le reconstruire
# à chaque modification.
TAILWIND_CLI_VERSION = "4.3.3"
TAILWIND_CLI_SRC_CSS = "assets/css/source.css"
TAILWIND_CLI_DIST_CSS = "css/tailwind.css"

# Validateur HTML du W3C, en local (#259) : `python manage.py install_validator`
# télécharge vnu.jar (paquet npm vnu-jar, intégrité vérifiée) dans .vnu/.
VNU_VERSION = "26.10.12"
VNU_INTEGRITY = (
    "sha512-Zg67G1zM28UGEVIOSn1ns6rFSZ6JVI/FNXhw+UJaXM02AQcDE84arp/b5c0OFrvzsgd/"
    "VcmpAd9B4hX38BeZvA=="
)

# Tests sans réseau : l'application ne fait aucune requête vers l'extérieur (#218).
TEST_RUNNER = "app_gestion.test_runner.NoNetworkTestRunner"

# Type des clés primaires

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
