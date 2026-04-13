"""
Django settings — Development environment.
"""

from .base import *  # noqa: F401, F403

DEBUG = True
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "0.0.0.0"]

# ──────────────────────────────────────────────
# Debug toolbar & browser reload
# ──────────────────────────────────────────────

INSTALLED_APPS += [  # noqa: F405
    "debug_toolbar",
    "django_browser_reload",
]

MIDDLEWARE.insert(0, "debug_toolbar.middleware.DebugToolbarMiddleware")  # noqa: F405
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
