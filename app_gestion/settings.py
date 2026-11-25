"""Réglages du projet : application locale et mono-utilisateur, réglages non
durcis (voir docs/architecture.md, « Contexte »)."""

import os
from pathlib import Path

from django.utils.csp import CSP

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
    "django.middleware.csp.ContentSecurityPolicyMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django_htmx.middleware.HtmxMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
# Le navigateur refuse toute image d'un autre serveur (#458) : seconde barrière, après le
# filtrage du HTML des notes. `data:` sert à l'éditeur (CodeMirror).
SECURE_CSP = {"img-src": [CSP.SELF, "data:"]}

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
                "core.context_processors.navigation",
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

# Adresses des fichiers statiques avec l'empreinte de leur contenu (#469) : après une mise
# à jour, le navigateur ne garde pas un ancien script.
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "core.static_files.VersionedStaticFilesStorage"},
}

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

# Fichier de log à rotation (#468), en plus de la console : `logs/app.log`, ou le dossier
# de la variable d'environnement `APP_GESTION_LOG_DIR`. Le texte des notes n'y est pas écrit.
LOG_DIR = Path(os.environ.get("APP_GESTION_LOG_DIR") or BASE_DIR / "logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)

_APP_LOGGER = {"handlers": ["console", "file"], "level": "INFO", "propagate": False}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "line": {"format": "%(asctime)s %(levelname)s %(name)s : %(message)s"}
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "line"},
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": LOG_DIR / "app.log",
            "formatter": "line",
            "encoding": "utf-8",
            "maxBytes": 2_000_000,
            "backupCount": 5,
            # Ouvert à la première ligne : rien n'est créé par une simple commande.
            "delay": True,
        },
    },
    "loggers": {
        "core": _APP_LOGGER,
        "images": _APP_LOGGER,
        "note_taking": _APP_LOGGER,
        "todolist": _APP_LOGGER,
        # Les 4xx et 5xx, que Django écrit déjà dans la console.
        "django.request": {"handlers": ["file"], "level": "WARNING"},
    },
}

# Tests sans réseau : l'application ne fait aucune requête vers l'extérieur (#218).
TEST_RUNNER = "app_gestion.test_runner.NoNetworkTestRunner"

# Type des clés primaires

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
