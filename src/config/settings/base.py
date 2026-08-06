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
    # Tableaux à colonnes typées dans les documents rédigés.
    # « typed_table_block » et non « table_block » : le second embarque
    # Handsontable, un tableur de plusieurs centaines de kilo-octets, pour
    # un usage où l'on saisit six lignes.
    "wagtail.contrib.typed_table_block",
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
    "apps.paiements",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# ──────────────────────────────────────────────
# Middleware
# ──────────────────────────────────────────────

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # Sous-classe de csp.middleware.CSPMiddleware : voir apps/core/middleware.py.
    "apps.core.middleware.CSPAvecAdminDjango",
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
                "apps.portail_enseignant.context_processors.propositions_en_attente",
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

# PBKDF2 à un million d'itérations prend plus de deux secondes sur le poste
# local de référence. Scrypt est mémoire-dur, fourni par Python sans dépendance
# supplémentaire, et divise ce temps par près de trois sur la même machine.
# Les formats historiques restent listés : Django les accepte puis les
# remplace automatiquement par scrypt après une connexion réussie.
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.ScryptPasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.BCryptSHA256PasswordHasher",
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

# Draftail reste l'éditeur natif de Wagtail. La liste est explicite pour que
# tous les champs RichTextField / RichTextBlock partagent le même profil et
# pour éviter qu'une mise à jour modifie silencieusement leur barre d'outils.
# « h1 » reste réservé au titre de page. Les embeds arbitraires sont exclus :
# la CSP stricte n'autorise pas les iframes éditoriales non contrôlées.
WAGTAILADMIN_RICH_TEXT_EDITORS = {
    "default": {
        "WIDGET": "wagtail.admin.rich_text.DraftailRichTextArea",
        "OPTIONS": {
            "features": [
                "h2",
                "h3",
                "h4",
                "h5",
                "h6",
                "bold",
                "italic",
                "underline",
                "strikethrough",
                "superscript",
                "subscript",
                "code",
                "ol",
                "ul",
                "blockquote",
                "align-left",
                "align-center",
                "align-right",
                "align-justify",
                "hr",
                "link",
                "document-link",
                "image",
            ]
        },
    }
}

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
EMAIL_HOST = env("EMAIL_HOST", default="")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
EMAIL_USE_SSL = env.bool("EMAIL_USE_SSL", default=False)
EMAIL_TIMEOUT = env.int("EMAIL_TIMEOUT", default=10)
EMAIL_TEST_RECIPIENT = env("EMAIL_TEST_RECIPIENT", default="")
SITE_URL = env("SITE_URL", default="http://localhost:8000")

# ──────────────────────────────────────────────
# Cloudflare Turnstile — protection des formulaires publics
# ──────────────────────────────────────────────

CLOUDFLARE_TURNSTILE_SITE_KEY = env("CLOUDFLARE_TURNSTILE_SITE_KEY", default="").strip()
CLOUDFLARE_TURNSTILE_SECRET_KEY = env("CLOUDFLARE_TURNSTILE_SECRET_KEY", default="").strip()
# Avec les deux clés, la protection s'active sans troisième variable. Le
# booléen reste disponible pour une désactivation d'urgence maîtrisée.
CLOUDFLARE_TURNSTILE_ENABLED = env.bool(
    "CLOUDFLARE_TURNSTILE_ENABLED",
    default=bool(CLOUDFLARE_TURNSTILE_SITE_KEY and CLOUDFLARE_TURNSTILE_SECRET_KEY),
)
CLOUDFLARE_TURNSTILE_TIMEOUT = env.float("CLOUDFLARE_TURNSTILE_TIMEOUT", default=5.0)

# ──────────────────────────────────────────────
# Celery
# ──────────────────────────────────────────────

CELERY_BROKER_URL = env("CELERY_BROKER_URL", default="redis://localhost:6379/0")
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default="redis://localhost:6379/0")
CELERY_TASK_ALWAYS_EAGER = env.bool("CELERY_TASK_ALWAYS_EAGER", default=False)
CELERY_TASK_EAGER_PROPAGATES = env.bool("CELERY_TASK_EAGER_PROPAGATES", default=False)
# Repli volontairement désactivé par défaut : en production, perdre le broker
# doit rester visible et ne doit pas créer des tâches dans le processus web.
DOCUMENTS_PDF_LOCAL_FALLBACK = False
CELERY_BROKER_CONNECTION_TIMEOUT = env.float("CELERY_BROKER_CONNECTION_TIMEOUT", default=0.5)
CELERY_BROKER_TRANSPORT_OPTIONS = {
    "socket_connect_timeout": CELERY_BROKER_CONNECTION_TIMEOUT,
    "socket_timeout": CELERY_BROKER_CONNECTION_TIMEOUT,
    "retry_on_timeout": False,
}
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
    # À heure creuse : la purge balaie une table écrite à chaque requête, et
    # le verrou qu'elle prend se paierait aux heures d'affluence.
    "core-purger-sessions": {
        "task": "core.purger_sessions",
        "schedule": crontab(hour=4, minute=0),
    },
    "core-purger-journal-audit": {
        "task": "core.purger_journal_audit",
        "schedule": 30 * 24 * 60 * 60,
    },
}

# Boutique de livres
COMMERCE_SEUIL_LIVRAISON_OFFERTE = env("COMMERCE_SEUIL_LIVRAISON_OFFERTE", default="150.00")
COMMERCE_ALERTE_EMAIL = env("COMMERCE_ALERTE_EMAIL", default="")
COMMERCE_REMISE_ETUDIANT = env("COMMERCE_REMISE_ETUDIANT", default="0.10")  # 10 %

# ──────────────────────────────────────────────
# Paiement en ligne — Stripe
# ──────────────────────────────────────────────
#
# Aucune donnée bancaire ne transite par nos serveurs : le paiement se fait sur
# une page hébergée par Stripe (Checkout). L'application ne voit jamais un
# numéro de carte, ce qui ramène le périmètre PCI au plus simple et laisse
# l'authentification forte à Stripe.
#
# La clé secrète et le secret de signature ne quittent jamais le serveur. Le
# secret de signature est ce qui distingue une notification réellement émise
# par Stripe d'un appel forgé : sans lui, n'importe qui pourrait déclarer un
# paiement abouti.
STRIPE_CLE_PUBLIABLE = env("STRIPE_CLE_PUBLIABLE", default="")
STRIPE_CLE_SECRETE = env("STRIPE_CLE_SECRETE", default="")
STRIPE_SECRET_WEBHOOK = env("STRIPE_SECRET_WEBHOOK", default="")
STRIPE_DEVISE = env("STRIPE_DEVISE", default="EUR")

# Taux de TVA proposé par défaut dans les formulaires de tarification. Il est
# saisi article par article : l'ITEAG peut relever de l'exonération de la
# formation professionnelle (taux 0) pour ses modules tout en facturant la TVA
# sur les livres.
PAIEMENTS_TAUX_TVA_DEFAUT = env("PAIEMENTS_TAUX_TVA_DEFAUT", default="0.00")

# Réservé aux instances de recette : laisse démarrer avec des clés « sk_test_ »
# hors DEBUG. Absent en production, où le contrôle paiements.E003 s'applique.
PAIEMENTS_AUTORISER_CLES_TEST = env.bool("PAIEMENTS_AUTORISER_CLES_TEST", default=False)

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

_turnstile_origins = ["https://challenges.cloudflare.com"] if CLOUDFLARE_TURNSTILE_ENABLED else []
_stripe_script_origins = ["https://js.stripe.com"]
_stripe_frame_origins = ["https://js.stripe.com", "https://hooks.stripe.com", "https://checkout.stripe.com"]
from csp.constants import NONCE  # noqa: E402

CONTENT_SECURITY_POLICY = {
    "DIRECTIVES": {
        "default-src": ["'self'"],
        # « NONCE » est une sentinelle de django-csp 4 : elle est remplacée à
        # chaque réponse par le nonce de la requête. Elle autorise un bloc en
        # ligne précis — la configuration JSON que les bundles Wagtail lisent au
        # démarrage — sans ouvrir « unsafe-inline » à toute la page. Un script
        # injecté ne connaît pas le nonce de la requête.
        #
        # Le premier jet déclarait « include-nonce-in », qui est la forme de
        # django-csp 3. La version 4 l'ignore **en silence** : le bloc portait
        # bien son attribut, l'en-tête ne le reprenait pas, et le navigateur
        # continuait de l'écarter.
        "script-src": [NONCE, "'self'", *_turnstile_origins, *_stripe_script_origins],
        "style-src": ["'self'", "'unsafe-inline'"],
        "img-src": ["'self'", "data:", "https://*.stripe.com"],
        "media-src": ["'self'", "blob:"],
        "font-src": ["'self'"],
        "connect-src": ["'self'", "https://api.stripe.com", "https://m.stripe.network"],
        "frame-src": [*_turnstile_origins, *_stripe_frame_origins],
        "object-src": ["'none'"],
        "base-uri": ["'self'"],
        "form-action": ["'self'"],
    },
}
