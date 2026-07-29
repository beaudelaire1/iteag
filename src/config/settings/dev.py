"""
Django settings — Development environment.
"""

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

DATABASES = {  # noqa: F811
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",  # noqa: F405
        # SQLite ne tolère qu'un écrivain à la fois. Avec `runserver` en
        # arrière-plan, une commande qui écrit longuement — un peuplement, une
        # migration de données — se heurte au verrou et abandonne au bout des
        # 5 secondes par défaut, sur un « database is locked » qui n'apprend
        # rien. On laisse le temps d'attendre son tour.
        "OPTIONS": {"timeout": 30},
    }
}

# ──────────────────────────────────────────────
# Static files
# ──────────────────────────────────────────────

STATICFILES_STORAGE = "django.contrib.staticfiles.storage.StaticFilesStorage"

# ──────────────────────────────────────────────
# Email — console in dev
# ──────────────────────────────────────────────

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
