"""
Django settings — Development environment.
"""

from pathlib import Path

from .base import *  # noqa: F401, F403

DEBUG = True
ELEARNING_AUTORISER_VIDEO_PUBLIQUE_EN_DEV = True
# "0.0.0.0" est nécessaire pour joindre le conteneur de développement depuis l'hôte.
# Ce réglage est propre à l'environnement de développement ; la production lit
# DJANGO_ALLOWED_HOSTS depuis l'environnement.
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "0.0.0.0"]  # noqa: S104

# ──────────────────────────────────────────────
# Outils de développement — désactivés par défaut pour garder le site rapide
# ──────────────────────────────────────────────

if env.bool("DJANGO_DEBUG_TOOLBAR", default=False):  # noqa: F405
    INSTALLED_APPS += ["debug_toolbar"]  # noqa: F405
    MIDDLEWARE.insert(0, "debug_toolbar.middleware.DebugToolbarMiddleware")  # noqa: F405

if env.bool("DJANGO_BROWSER_RELOAD", default=False):  # noqa: F405
    INSTALLED_APPS += ["django_browser_reload"]  # noqa: F405
    MIDDLEWARE.append("django_browser_reload.middleware.BrowserReloadMiddleware")  # noqa: F405

INTERNAL_IPS = ["127.0.0.1"]

DEBUG_TOOLBAR_CONFIG = {
    "INTERCEPT_REDIRECTS": False,
}

# ──────────────────────────────────────────────
# Database — SQLite for fast local dev
# ──────────────────────────────────────────────

if not env("DATABASE_URL", default=""):  # noqa: F405
    DATABASES = {  # noqa: F811
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",  # noqa: F405
        }
    }

# L'URL explicite peut elle-même désigner SQLite. On lui applique donc les
# options locales après sa lecture, tout en laissant PostgreSQL intact dans
# Docker. SQLite ne tolère qu'un écrivain à la fois : WAL évite qu'une écriture
# de session bloque les lectures concurrentes, et NORMAL évite une
# synchronisation complète pour chaque petite transaction sans compromettre
# l'intégrité du journal.
if DATABASES["default"]["ENGINE"] == "django.db.backends.sqlite3":  # noqa: F405
    nom_sqlite = DATABASES["default"]["NAME"]  # noqa: F405
    if nom_sqlite != ":memory:" and not Path(nom_sqlite).is_absolute():
        # django-environ conserve les chemins SQLite relatifs tels quels. Sans
        # normalisation, lancer manage.py depuis la racine crée une seconde
        # base vide à côté de src/ au lieu d'ouvrir la base locale attendue.
        DATABASES["default"]["NAME"] = BASE_DIR / nom_sqlite  # noqa: F405
    DATABASES["default"].setdefault("OPTIONS", {}).update(  # noqa: F405
        {
            "timeout": 30,
            "init_command": "PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL",
        }
    )

# Le fichier .env local peut contenir les clés destinées au futur déploiement
# sans transformer chaque connexion localhost en aller-retour Cloudflare.
# L'activation en développement reste possible, mais doit être explicite.
CLOUDFLARE_TURNSTILE_ENABLED = env.bool("CLOUDFLARE_TURNSTILE_ENABLED", default=False)  # noqa: F405

# En local, la session a une durée absolue de 30 minutes au lieu de réécrire
# SQLite à chaque page. C'est plus strict que la durée glissante de production
# et supprime trois opérations SQL sur chaque requête authentifiée.
SESSION_SAVE_EVERY_REQUEST = False

# ──────────────────────────────────────────────
# Static files
# ──────────────────────────────────────────────

STATICFILES_STORAGE = "django.contrib.staticfiles.storage.StaticFilesStorage"

# Les emails restent visibles dans la console tant que les identifiants SMTP
# ne sont pas renseignés dans le fichier .env local.
if not EMAIL_HOST or not EMAIL_HOST_USER or not EMAIL_HOST_PASSWORD:  # noqa: F405
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# ──────────────────────────────────────────────
# Axes — relaxed in dev
# ──────────────────────────────────────────────

AXES_ENABLED = False

# ──────────────────────────────────────────────
# CSP — report only in dev
# ──────────────────────────────────────────────

CONTENT_SECURITY_POLICY = None
CONTENT_SECURITY_POLICY_REPORT_ONLY = None
