"""
Django settings — ITEAG Platform
Base configuration shared across all environments.
"""

from pathlib import Path

import environ
from celery.schedules import crontab

# ──────────────────────────────────────────────
# Paths
# ──────────────────────────────────────────────

BASE_DIR = Path(__file__).resolve().parent.parent.parent  # src/
APPS_DIR = BASE_DIR / "apps"

env = environ.Env()
env.read_env(str(BASE_DIR / ".env"))

# ──────────────────────────────────────────────
# Core
# ──────────────────────────────────────────────

SECRET_KEY = env("DJANGO_SECRET_KEY", default="change-me-in-production")
DEBUG = env.bool("DJANGO_DEBUG", default=False)
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=[])
CSRF_TRUSTED_ORIGINS = env.list("DJANGO_CSRF_TRUSTED_ORIGINS", default=[])

# ──────────────────────────────────────────────
# Applications
# ──────────────────────────────────────────────

DJANGO_APPS = [
    "jazzmin",  # Avant django.contrib.admin
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
    "django.contrib.sites",
]

THIRD_PARTY_APPS = [
    "wagtail.contrib.forms",
    "wagtail.contrib.redirects",
    "wagtail.embeds",
    "wagtail.sites",
    "wagtail.users",
    "wagtail.snippets",
    "wagtail.documents",
    "wagtail.images",
    "wagtail.search",
    "wagtail.admin",
    "wagtail",
    "modelcluster",
    "taggit",
    "storages",
    "csp",
    "axes",
    "django_celery_results",
]

LOCAL_APPS = [
    "apps.core.apps.CoreConfig",
    "apps.accounts.apps.AccountsConfig",
    "apps.formations.apps.FormationsConfig",
    "apps.admissions.apps.AdmissionsConfig",
    "apps.academics.apps.AcademicsConfig",
    "apps.lms.apps.LmsConfig",
    "apps.elearning.apps.ElearningConfig",
    "apps.library.apps.LibraryConfig",
    "apps.website.apps.WebsiteConfig",
    "apps.administration.apps.AdministrationConfig",
    "apps.documents.apps.DocumentsConfig",
    "apps.portail_etudiant.apps.PortailEtudiantConfig",
    "apps.portail_enseignant.apps.PortailEnseignantConfig",
    "apps.commerce.apps.CommerceConfig",
    "apps.paiements.apps.PaiementsConfig",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

SITE_ID = 1

# ──────────────────────────────────────────────
# Middleware
# ──────────────────────────────────────────────

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "apps.core.middleware.RafraichissementSessionMiddleware",
    "apps.accounts.middleware.MFARequiredMiddleware",
    "axes.middleware.AxesMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.core.middleware.CSPAvecAdminDjango",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

# ──────────────────────────────────────────────
# Templates
# ──────────────────────────────────────────────

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.core.context_processors.site_settings",
                "apps.core.context_processors.notifications",
            ],
        },
    },
]

# ──────────────────────────────────────────────
# Database
# ──────────────────────────────────────────────

DATABASES = {
    "default": env.db(
        "DATABASE_URL",
        default="postgresql://iteag:iteag_dev@localhost:5432/iteag",
    )
}
DATABASES["default"]["CONN_MAX_AGE"] = 60
DATABASES["default"]["CONN_HEALTH_CHECKS"] = True

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ──────────────────────────────────────────────
# Authentication
# ──────────────────────────────────────────────

AUTH_USER_MODEL = "accounts.User"
LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "accounts:dashboard_redirect"
LOGOUT_REDIRECT_URL = "website:home"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 12}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ──────────────────────────────────────────────
# Internationalisation
# ──────────────────────────────────────────────

LANGUAGE_CODE = "fr-fr"
TIME_ZONE = "America/Cayenne"
USE_I18N = True
USE_TZ = True

# ──────────────────────────────────────────────
# Static & Media
# ──────────────────────────────────────────────

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

# WhiteNoise sert les statiques en production (voir settings/prod.py)
WHITENOISE_MAX_AGE = 31536000
WHITENOISE_IMMUTABLE_FILE_TEST = r"^.+\.[0-9a-f]{12}\..+$"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# ──────────────────────────────────────────────
# Email
# ──────────────────────────────────────────────

EMAIL_BACKEND = env("EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend")
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="ITEAG <noreply@iteag.org>")
SERVER_EMAIL = env("SERVER_EMAIL", default=DEFAULT_FROM_EMAIL)
EMAIL_HOST = env("EMAIL_HOST", default="")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
EMAIL_USE_SSL = env.bool("EMAIL_USE_SSL", default=False)
EMAIL_TIMEOUT = env.int("EMAIL_TIMEOUT", default=10)

# ──────────────────────────────────────────────
# Wagtail
# ──────────────────────────────────────────────

WAGTAIL_SITE_NAME = "ITEAG"
WAGTAILADMIN_BASE_URL = env("WAGTAILADMIN_BASE_URL", default="http://localhost:8000")

# ──────────────────────────────────────────────
# Cache / Celery
# ──────────────────────────────────────────────

REDIS_URL = env("REDIS_URL", default="redis://localhost:6379/0")
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
        "TIMEOUT": 300,
    }
}

CELERY_BROKER_URL = env("CELERY_BROKER_URL", default="redis://localhost:6379/1")
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default="redis://localhost:6379/2")
CELERY_TASK_ALWAYS_EAGER = env.bool("CELERY_TASK_ALWAYS_EAGER", default=False)
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 300
CELERY_TASK_SOFT_TIME_LIMIT = 270
CELERY_TIMEZONE = TIME_ZONE
CELERY_BEAT_SCHEDULE = {
    "coeur-heartbeat": {
        "task": "core.heartbeat",
        "schedule": 60.0,
    },
    "coeur-purge-journal-audit": {
        "task": "core.purger_journal_audit",
        "schedule": crontab(hour=3, minute=20, day_of_month="1"),
    },
    "elearning-purge-journal-acces": {
        "task": "elearning.purger_journal_acces",
        "schedule": crontab(hour=3, minute=40, day_of_month="1"),
    },
    "paiements-minimiser-charges-utiles": {
        "task": "paiements.minimiser_charges_utiles",
        "schedule": crontab(hour=3, minute=50),
    },
    "paiements-reparer-livraisons": {
        "task": "paiements.reparer_livraisons",
        "schedule": crontab(minute="*/15"),
    },
    "commerce-expirer-devis-livraison": {
        "task": "commerce.expirer_devis_livraison",
        "schedule": crontab(hour=2, minute=50),
    },
}

# ──────────────────────────────────────────────
# Retention
# ──────────────────────────────────────────────

RETENTION_JOURNAL_AUDIT_JOURS = 365
RETENTION_JOURNAL_ACCES_VIDEO_JOURS = 90
RETENTION_CHARGE_UTILE_STRIPE_JOURS = 90

# ──────────────────────────────────────────────
# Stripe
# ──────────────────────────────────────────────

STRIPE_CLE_PUBLIABLE = env("STRIPE_CLE_PUBLIABLE", default="")
STRIPE_CLE_SECRETE = env("STRIPE_CLE_SECRETE", default="")
STRIPE_SECRET_WEBHOOK = env("STRIPE_SECRET_WEBHOOK", default="")
STRIPE_DEVISE = env("STRIPE_DEVISE", default="EUR")

# ──────────────────────────────────────────────
# Site public
# ──────────────────────────────────────────────

SITE_URL = env("SITE_URL", default="http://localhost:8000").rstrip("/")
SITE_NAME = "ITEAG"
SITE_TAGLINE = "Institut de Théologie Évangélique des Antilles et de la Guyane"
SITE_EMAIL = env("SITE_EMAIL", default="contact@iteag.org")
SITE_PHONE = env("SITE_PHONE", default="")
SITE_ADDRESS = env("SITE_ADDRESS", default="")
SITE_SIRET = env("SITE_SIRET", default="")
SITE_FORME_JURIDIQUE = env("SITE_FORME_JURIDIQUE", default="")
SITE_RESPONSABLE_PUBLICATION = env("SITE_RESPONSABLE_PUBLICATION", default="")
SITE_HEBERGEUR = env("SITE_HEBERGEUR", default="")
SITE_HEBERGEUR_ADRESSE = env("SITE_HEBERGEUR_ADRESSE", default="")

# ──────────────────────────────────────────────
# Admissions
# ──────────────────────────────────────────────

CLOUDFLARE_TURNSTILE_ENABLED = env.bool("CLOUDFLARE_TURNSTILE_ENABLED", default=False)
CLOUDFLARE_TURNSTILE_SITE_KEY = env("CLOUDFLARE_TURNSTILE_SITE_KEY", default="")
CLOUDFLARE_TURNSTILE_SECRET_KEY = env("CLOUDFLARE_TURNSTILE_SECRET_KEY", default="")
CLOUDFLARE_TURNSTILE_TIMEOUT = env.int("CLOUDFLARE_TURNSTILE_TIMEOUT", default=5)

# ──────────────────────────────────────────────
# Bibliothèque / Commerce / E-learning
# ──────────────────────────────────────────────

BUNNY_ZONE_DIFFUSION = env("BUNNY_ZONE_DIFFUSION", default="").strip().rstrip("/")
if BUNNY_ZONE_DIFFUSION and "://" not in BUNNY_ZONE_DIFFUSION:
    BUNNY_ZONE_DIFFUSION = f"https://{BUNNY_ZONE_DIFFUSION}"
BUNNY_CLE_SIGNATURE = env("BUNNY_CLE_SIGNATURE", default="")
BUNNY_LIER_ADRESSE_IP = env.bool("BUNNY_LIER_ADRESSE_IP", default=False)
BUNNY_STREAM_LIBRARY_ID = env("BUNNY_STREAM_LIBRARY_ID", default="").strip()
BUNNY_STREAM_API_KEY = env("BUNNY_STREAM_API_KEY", default="").strip()
ELEARNING_FLUX_SIMULTANES_MAX = env.int("ELEARNING_FLUX_SIMULTANES_MAX", default=1)
ELEARNING_FLUX_TTL = 900
ELEARNING_INTERVALLE_SIGNAL = 15

# ──────────────────────────────────────────────
# Session
# ──────────────────────────────────────────────

SESSION_ENGINE = "django.contrib.sessions.backends.db"
SESSION_COOKIE_AGE = 1800
SESSION_SAVE_EVERY_REQUEST = True

# ──────────────────────────────────────────────
# Content Security Policy (django-csp)
# ──────────────────────────────────────────────

_turnstile_origins = ["https://challenges.cloudflare.com"] if CLOUDFLARE_TURNSTILE_ENABLED else []
_stripe_script_origins = ["https://js.stripe.com"]
_stripe_frame_origins = ["https://js.stripe.com", "https://hooks.stripe.com", "https://checkout.stripe.com"]
from csp.constants import NONCE  # noqa: E402

CONTENT_SECURITY_POLICY = {
    "DIRECTIVES": {
        "default-src": ["'self'"],
        "script-src": ["'self'", *_turnstile_origins, *_stripe_script_origins],
        "style-src": ["'self'"],
        "style-src-elem": ["'self'"],
        "style-src-attr": ["'none'"],
        "img-src": ["'self'", "data:", "https://*.stripe.com"],
        "font-src": ["'self'"],
        "connect-src": ["'self'", "https://api.stripe.com", "https://m.stripe.network"],
        "frame-src": [*_turnstile_origins, *_stripe_frame_origins],
        "object-src": ["'none'"],
        "base-uri": ["'self'"],
        "form-action": ["'self'"],
        "frame-ancestors": ["'none'"],
    }
}

# Les handlers d'administration tiers contiennent quelques scripts inline. La
# politique globale reste sans unsafe-inline : le middleware limite l'exception
# à l'interface Django Admin authentifiée et non au site public.
DJANGO_ADMIN_SCRIPT_NONCE = NONCE

# ──────────────────────────────────────────────
# Axes / MFA / Sécurité applicative
# ──────────────────────────────────────────────

AXES_FAILURE_LIMIT = 5
AXES_COOLOFF_TIME = 1
AXES_RESET_ON_SUCCESS = True
AXES_LOCKOUT_PARAMETERS = [["username", "ip_address"]]

# ──────────────────────────────────────────────
# Draftail
# ──────────────────────────────────────────────

WAGTAILADMIN_RICH_TEXT_EDITORS = {
    "default": {
        "WIDGET": "apps.core.editeur_riche.DraftailPortailWidget",
    },
}

# ──────────────────────────────────────────────
# Journalisation
# ──────────────────────────────────────────────

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "()": "pythonjsonlogger.json.JsonFormatter",
            "format": "%(asctime)s %(levelname)s %(name)s %(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json",
        },
    },
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "django.security": {"handlers": ["console"], "level": "WARNING", "propagate": False},
        "apps": {"handlers": ["console"], "level": "INFO", "propagate": False},
    },
}
