"""
Django settings — Test environment.
"""

from .base import *  # noqa: F401, F403

DEBUG = False
SECRET_KEY = "test-secret-key-not-for-production"

# Les tests locaux restent instantanés avec SQLite. En CI, DATABASE_URL est
# fourni et la suite exerce réellement PostgreSQL, comme en production.
if not env("DATABASE_URL", default=""):  # noqa: F405
    DATABASES = {  # noqa: F811
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": ":memory:",
        }
    }

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

STATICFILES_STORAGE = "django.contrib.staticfiles.storage.StaticFilesStorage"

AXES_ENABLED = False

# Le second facteur est vérifié par ses propres tests, qui le réactivent
# explicitement. L'imposer partout obligerait chaque test d'espace
# administratif à jouer l'enrôlement, sans rien démontrer de plus.
OTP_ENFORCE = False

CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

WAGTAIL_ENABLE_UPDATE_CHECK = False

CONTENT_SECURITY_POLICY = None
CONTENT_SECURITY_POLICY_REPORT_ONLY = None
