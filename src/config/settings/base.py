"""
Django settings — ITEAG Platform
Base configuration shared across all environments.
"""

from pathlib import Path

import environ

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

# ──────────────────────────────────────────────
# Apps
# ──────────────────────────────────────────────

DJANGO_APPS = [
    "jazzmin",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sitemaps",
]

THIRD_PARTY_APPS = [
    "wagtail.contrib.forms",
    "wagtail.contrib.redirects",
    "wagtail.contrib.sitemaps",
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
    "django_htmx",
    "axes",
    "csp",
    "django_otp",
    "django_otp.plugins.otp_totp",
    "django_otp.plugins.otp_static",
]

LOCAL_APPS = [
    "apps.core",
    "apps.accounts",
    "apps.administration",
    "apps.website",
    "apps.formations",
    "apps.admissions",
    "apps.academics",
    "apps.portail_etudiant",
    "apps.portail_enseignant",
    "apps.lms",
    "apps.library",
    "apps.documents",
    "apps.elearning",
    "apps.commerce",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# ──────────────────────────────────────────────
# Middleware
# ──────────────────────────────────────────────

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "csp.middleware.CSPMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django_otp.middleware.OTPMiddleware",
    "apps.accounts.middleware.Force2FAStaffMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django_htmx.middleware.HtmxMiddleware",
    "wagtail.contrib.redirects.middleware.RedirectMiddleware",
    "axes.middleware.AxesMiddleware",
]

# ──────────────────────────────────────────────
# URLs & WSGI
# ──────────────────────────────────────────────

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

# ──────────────────────────────────────────────
# Templates
# ──────────────────────────────────────────────

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [
            BASE_DIR / "templates",
        ],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.core.context_processors.site_context",
                "apps.core.context_processors.navigation_publique",
                "apps.core.context_processors.notifications_context",
                "apps.administration.context_processors.taches_en_attente",
                "apps.commerce.context_processors.panier_context",
            ],
        },
    },
]

# ──────────────────────────────────────────────
# Database
# ──────────────────────────────────────────────

DATABASES = {
    "default": env.db("DATABASE_URL", default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}"),
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ──────────────────────────────────────────────
# Authentication
# ──────────────────────────────────────────────

AUTH_USER_MODEL = "accounts.User"

AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",
    "django.contrib.auth.backends.ModelBackend",
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 12}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "/connexion/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/"

# ──────────────────────────────────────────────
# Axes (brute force protection)
# ──────────────────────────────────────────────

# ──────────────────────────────────────────────
# Double authentification (django-otp)
# ──────────────────────────────────────────────

OTP_TOTP_ISSUER = "ITEAG"
OTP_ENFORCE = env.bool("DJANGO_OTP_ENFORCE", default=True)
# Rôles pour lesquels le second facteur est obligatoire (audit du CDC v1 §5).
ROLES_2FA_OBLIGATOIRE = ["admin", "secretariat"]

# ──────────────────────────────────────────────
# Axes (brute force protection)
# ──────────────────────────────────────────────

AXES_FAILURE_LIMIT = 5
AXES_COOLOFF_TIME = 0.5  # 30 minutes
AXES_LOCKOUT_PARAMETERS = ["username"]
AXES_RESET_ON_SUCCESS = True

# ──────────────────────────────────────────────
# Internationalization
# ──────────────────────────────────────────────

LANGUAGE_CODE = "fr-fr"
TIME_ZONE = "America/Guadeloupe"
USE_I18N = True
USE_TZ = True

# ──────────────────────────────────────────────
# Static & Media
# ──────────────────────────────────────────────

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [
    BASE_DIR / "static",
]

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# ──────────────────────────────────────────────
# Jazzmin (Django Admin theme)
# ──────────────────────────────────────────────

JAZZMIN_SETTINGS = {
    "site_title": "ITEAG Admin",
    "site_header": "ITEAG",
    "site_brand": "ITEAG",
    "site_logo": None,
    "login_logo": None,
    "welcome_sign": "Administration ITEAG",
    "copyright": "ITEAG — Institut de Théologie Évangélique des Antilles et de la Guyane",
    "search_model": ["accounts.User"],
    "topmenu_links": [
        {"name": "Accueil site", "url": "/", "new_window": True},
        {"name": "Portail admin", "url": "/espace-admin/"},
    ],
    "show_sidebar": True,
    "navigation_expanded": True,
    "icons": {
        "auth": "fas fa-users-cog",
        "accounts.User": "fas fa-user",
        "formations.Parcours": "fas fa-graduation-cap",
        "formations.Cours": "fas fa-book",
        "formations.Professeur": "fas fa-chalkboard-teacher",
        "formations.Discipline": "fas fa-layer-group",
        "formations.Tarif": "fas fa-euro-sign",
        "academics.SessionAcademique": "fas fa-calendar-alt",
        "academics.ProfilEtudiant": "fas fa-user-graduate",
        "academics.Promotion": "fas fa-users",
        "academics.Paiement": "fas fa-credit-card",
        "admissions.DossierCandidature": "fas fa-file-alt",
        "library.NoticeBibliographique": "fas fa-book-open",
        "documents.DocumentAdministratif": "fas fa-folder-open",
        "commerce.ProduitLivre": "fas fa-book",
        "commerce.Commande": "fas fa-shopping-cart",
        "commerce.MouvementStock": "fas fa-boxes",
        "commerce.AlerteStock": "fas fa-exclamation-triangle",
    },
    "default_icon_parents": "fas fa-folder",
    "default_icon_children": "fas fa-circle",
    "related_modal_active": True,
    "custom_css": None,
    "custom_js": None,
    "use_google_fonts_cdn": False,
    "show_ui_builder": False,
    "changeform_format": "horizontal_tabs",
}

JAZZMIN_UI_TWEAKS = {
    "navbar_small_text": False,
    "footer_small_text": False,
    "body_small_text": False,
    "brand_small_text": False,
    "brand_colour": False,
    "accent": "accent-navy",
    "navbar": "navbar-dark",
    "no_navbar_border": False,
    "navbar_fixed": True,
    "layout_boxed": False,
    "footer_fixed": False,
    "sidebar_fixed": True,
    "sidebar": "sidebar-dark-primary",
    "sidebar_nav_small_text": False,
    "sidebar_disable_expand": False,
    "sidebar_nav_child_indent": True,
    "sidebar_nav_compact_style": False,
    "sidebar_nav_legacy_style": False,
    "sidebar_nav_flat_style": False,
    "theme": "default",
    "dark_mode_theme": None,
    "button_classes": {
        "primary": "btn-primary",
        "secondary": "btn-secondary",
        "info": "btn-info",
        "warning": "btn-warning",
        "danger": "btn-danger",
        "success": "btn-success",
    },
}

# ──────────────────────────────────────────────
# Wagtail
# ──────────────────────────────────────────────

WAGTAIL_SITE_NAME = "ITEAG"
WAGTAILADMIN_BASE_URL = env("WAGTAILADMIN_BASE_URL", default="http://localhost:8000")
WAGTAIL_ENABLE_UPDATE_CHECK = False
WAGTAILIMAGES_MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10 Mo
WAGTAILDOCS_EXTENSIONS = ["pdf", "docx", "doc", "pptx", "xlsx", "csv", "txt"]

# ──────────────────────────────────────────────
# Security defaults (overridden per env)
# ──────────────────────────────────────────────

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_HTTPONLY = True
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True

# ──────────────────────────────────────────────
# File upload limits
# ──────────────────────────────────────────────

FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024  # 10 Mo
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024

# ──────────────────────────────────────────────
# Email
# ──────────────────────────────────────────────

EMAIL_BACKEND = env("EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend")
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="secretariat@iteag.org")
SERVER_EMAIL = env("SERVER_EMAIL", default="errors@iteag.org")
SITE_URL = env("SITE_URL", default="http://localhost:8000")

# ──────────────────────────────────────────────
# Celery
# ──────────────────────────────────────────────

CELERY_BROKER_URL = env("CELERY_BROKER_URL", default="redis://localhost:6379/0")
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default="redis://localhost:6379/0")
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE
CELERY_BEAT_SCHEDULE = {
    "elearning-expirer-acces": {
        "task": "elearning.expirer_acces",
        "schedule": 24 * 60 * 60,
    },
    "commerce-verifier-stocks": {
        "task": "commerce.verifier_stocks",
        "schedule": 6 * 60 * 60,
    },
    "core-purger-notifications": {
        "task": "core.purger_notifications",
        "schedule": 7 * 24 * 60 * 60,
    },
    "core-purger-journal-audit": {
        "task": "core.purger_journal_audit",
        "schedule": 30 * 24 * 60 * 60,
    },
}

# Boutique de livres
COMMERCE_FRAIS_LIVRAISON = env("COMMERCE_FRAIS_LIVRAISON", default="0.00")
COMMERCE_ALERTE_EMAIL = env("COMMERCE_ALERTE_EMAIL", default="")

# ──────────────────────────────────────────────
# Formation vidéo (voir ADR-001 et ADR-002)
# ──────────────────────────────────────────────

# Fournisseur de diffusion des modules protégés — voir ADR-005.
# Les nouveaux médias sont toujours référencés chez un fournisseur externe.
# "local" et "s3" ne subsistent que pour relire d'anciennes références.
ELEARNING_DIFFUSION_VIDEO = env("ELEARNING_DIFFUSION_VIDEO", default="bunny")
# Ancien nom, conservé le temps que les environnements soient mis à jour.
ELEARNING_STOCKAGE_VIDEO = ELEARNING_DIFFUSION_VIDEO

# Fournisseurs admis pour le contenu public (bandes-annonces du catalogue).
# Ils ne protègent rien : le modèle refuse de les rattacher à un module
# restreint, cette liste ne sert qu'à autoriser leurs origines dans la CSP.
ELEARNING_DIFFUSION_PUBLIQUE = env.list("ELEARNING_DIFFUSION_PUBLIQUE", default=["youtube", "vimeo"])

# Dérogation de démonstration lue par le modèle uniquement lorsque DEBUG=True.
# Elle ne peut donc jamais assouplir la sécurité d'une instance de production.
ELEARNING_AUTORISER_VIDEO_PUBLIQUE_EN_DEV = False

AWS_STORAGE_BUCKET_NAME_VIDEOS = env("AWS_STORAGE_BUCKET_NAME_VIDEOS", default="iteag-videos")

# Bunny Stream. La clé de signature ne quitte jamais le serveur : elle sert à
# calculer les jetons de lecture, jamais à être transmise au navigateur.
BUNNY_ZONE_DIFFUSION = env("BUNNY_ZONE_DIFFUSION", default="").strip().rstrip("/")
# Compatibilité avec les configurations déjà saisies sous la forme
# « vz-xxxx.b-cdn.net ». Une origine de diffusion doit être absolue dans le
# navigateur ; sans schéma, elle devient une adresse relative au site et aucun
# manifeste HLS ne peut être chargé.
if BUNNY_ZONE_DIFFUSION and "://" not in BUNNY_ZONE_DIFFUSION:
    BUNNY_ZONE_DIFFUSION = f"https://{BUNNY_ZONE_DIFFUSION}"
BUNNY_CLE_SIGNATURE = env("BUNNY_CLE_SIGNATURE", default="")
# Liaison du jeton à l'adresse IP : plus strict, mais coupe la lecture quand
# l'adresse change en cours de séance — fréquent en mobile.
BUNNY_LIER_ADRESSE_IP = env.bool("BUNNY_LIER_ADRESSE_IP", default=False)

# Nombre de lectures simultanées tolérées par compte. 1 = un seul appareil à la
# fois, ce qui rend le partage de compte inconfortable sans gêner un usage normal.
ELEARNING_FLUX_SIMULTANES_MAX = env.int("ELEARNING_FLUX_SIMULTANES_MAX", default=1)
ELEARNING_FLUX_TTL = 900

# Intervalle des signaux de progression envoyés par le lecteur (secondes).
ELEARNING_INTERVALLE_SIGNAL = 15

# ──────────────────────────────────────────────
# Session
# ──────────────────────────────────────────────

SESSION_ENGINE = "django.contrib.sessions.backends.db"
SESSION_COOKIE_AGE = 1800  # 30 minutes
SESSION_SAVE_EVERY_REQUEST = True

# ──────────────────────────────────────────────
# Content Security Policy (django-csp)
# ──────────────────────────────────────────────

CONTENT_SECURITY_POLICY = {
    "DIRECTIVES": {
        "default-src": ["'self'"],
        "script-src": ["'self'"],
        "style-src": ["'self'", "'unsafe-inline'"],
        "img-src": ["'self'", "data:"],
        "media-src": ["'self'", "blob:"],
        "font-src": ["'self'"],
        "connect-src": ["'self'"],
        "frame-src": ["'none'"],
        "object-src": ["'none'"],
        "base-uri": ["'self'"],
        "form-action": ["'self'"],
    },
}
