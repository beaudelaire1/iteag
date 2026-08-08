"""
Django settings — Production environment.
"""

from copy import deepcopy

from .base import *  # noqa: F401, F403

# `from .base import *` lie les objets mutables par référence. Les modifier en
# place ici (MIDDLEWARE.insert, ajout d'une tâche Beat, extension de la CSP...)
# muterait aussi `config.settings.base` et toute configuration déjà construite
# à partir d'elle dans le même processus — notamment les tests qui importent
# ponctuellement `prod.py`. Chaque structure que la production enrichit reçoit
# donc sa propre copie avant la première mutation.
DATABASES = deepcopy(DATABASES)  # noqa: F405
MIDDLEWARE = list(MIDDLEWARE)  # noqa: F405
CELERY_BEAT_SCHEDULE = deepcopy(CELERY_BEAT_SCHEDULE)  # noqa: F405
CONTENT_SECURITY_POLICY = deepcopy(CONTENT_SECURITY_POLICY)  # noqa: F405

DEBUG = False
SECRET_KEY = env("DJANGO_SECRET_KEY")  # noqa: F405
# django-environ met « django.db.backends.postgresql » (psycopg2).
# Le projet utilise psycopg v3 → forcer le bon backend.
DATABASES["default"]["ENGINE"] = "django.db.backends.postgresql"
# psycopg v3 est compatible via le même backend depuis Django 4.2+
# à condition que psycopg (et non psycopg2) soit installé.
DATABASES["default"]["CONN_MAX_AGE"] = env.int("DATABASE_CONN_MAX_AGE", default=60)  # noqa: F405
DATABASES["default"]["CONN_HEALTH_CHECKS"] = True

# django-treebeard 5.3 signale que les managers actuels de Wagtail devront
# évoluer avant Treebeard 6. Wagtail 7.4 LTS supporte officiellement Treebeard
# 4.8–5.x et le verrou de production reste en 5.x : ce warning tiers n'est donc
# pas une anomalie de la release actuelle. On ne neutralise que son identifiant
# précis afin que `check --deploy --fail-level WARNING` reste strict sur tous
# les autres avertissements. À retirer lors d'un futur passage à Treebeard 6.
SILENCED_SYSTEM_CHECKS = ["treebeard.E001"]

# ──────────────────────────────────────────────
# Security — production hardened
# ──────────────────────────────────────────────

SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Une session reste valable 30 minutes après la dernière activité, mais elle ne
# doit pas être réécrite dans PostgreSQL à chaque requête. Le middleware dédié
# la touche périodiquement, ce qui conserve l'expiration glissante.
SESSION_SAVE_EVERY_REQUEST = False
SESSION_REFRESH_INTERVAL = env.int("SESSION_REFRESH_INTERVAL", default=300)  # noqa: F405
_index_auth = MIDDLEWARE.index("django.contrib.auth.middleware.AuthenticationMiddleware")
MIDDLEWARE.insert(_index_auth + 1, "apps.core.middleware.RafraichissementSessionMiddleware")

# Beat publie un heartbeat court ; le healthcheck du conteneur vérifie qu'il est
# encore renouvelé. La sonde web /healthz reste volontairement limitée à la
# base et au cache pour ne pas redémarrer le serveur web lors d'une panne Celery.
CELERY_BEAT_SCHEDULE["core-heartbeat-celery"] = {
    "task": "core.heartbeat_celery",
    "schedule": 60.0,
}

# ──────────────────────────────────────────────
# Static files — WhiteNoise + manifest
# ──────────────────────────────────────────────

MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")
STORAGES = {
    "staticfiles": {
        # Manifeste strict, à une liste d'exceptions déclarées près : voir
        # « apps/core/stockage.py ». Le stockage nu faisait répondre 500 à
        # toutes les pages de /django-admin/ en production.
        "BACKEND": "apps.core.stockage.StockageStatiquesITEAG",
    },
}

# ──────────────────────────────────────────────
# Media — S3
# ──────────────────────────────────────────────

AWS_ACCESS_KEY_ID = env("AWS_ACCESS_KEY_ID", default="")  # noqa: F405
AWS_SECRET_ACCESS_KEY = env("AWS_SECRET_ACCESS_KEY", default="")  # noqa: F405
AWS_STORAGE_BUCKET_NAME = env("AWS_STORAGE_BUCKET_NAME", default="iteag-media")  # noqa: F405
AWS_S3_ENDPOINT_URL = env("AWS_S3_ENDPOINT_URL", default="")  # noqa: F405
AWS_S3_REGION_NAME = env("AWS_S3_REGION_NAME", default="auto" if AWS_S3_ENDPOINT_URL else "eu-west-3")  # noqa: F405
AWS_S3_ADDRESSING_STYLE = env("AWS_S3_ADDRESSING_STYLE", default="path")  # noqa: F405
AWS_S3_SIGNATURE_VERSION = "s3v4"
AWS_S3_CUSTOM_DOMAIN = env("AWS_S3_CUSTOM_DOMAIN", default="") or None  # noqa: F405
AWS_DEFAULT_ACL = None
AWS_QUERYSTRING_AUTH = True
AWS_QUERYSTRING_EXPIRE = env.int("AWS_QUERYSTRING_EXPIRE", default=3600)  # noqa: F405
# Deux dépôts de même nom ne doivent pas s'écraser : un devoir remis
# effacerait celui d'un autre étudiant.
AWS_S3_FILE_OVERWRITE = False
AWS_S3_OBJECT_PARAMETERS = {"CacheControl": "max-age=86400"}

STORAGES["default"] = {
    "BACKEND": "storages.backends.s3boto3.S3Boto3Storage",
}

# Les médias (images Wagtail, pièces jointes) sont servis depuis l'origine du
# bucket R2 en URL signée : la CSP globale ne connaît que 'self' et Stripe,
# le navigateur bloquerait chaque <img> sans cette ouverture.
_origine_medias = f"https://{AWS_S3_CUSTOM_DOMAIN}" if AWS_S3_CUSTOM_DOMAIN else AWS_S3_ENDPOINT_URL
if _origine_medias:
    for _directive in ("img-src", "media-src"):
        CONTENT_SECURITY_POLICY["DIRECTIVES"][_directive].append(_origine_medias)


# ──────────────────────────────────────────────
# Cache — Redis
# ──────────────────────────────────────────────

CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": env("REDIS_URL", default="redis://localhost:6379/1"),  # noqa: F405
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
        },
    }
}

# ──────────────────────────────────────────────
# Sentry
# ──────────────────────────────────────────────

import sentry_sdk  # noqa: E402
from sentry_sdk.integrations.django import DjangoIntegration  # noqa: E402

SENTRY_DSN = env("SENTRY_DSN", default="")  # noqa: F405
if SENTRY_DSN:
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[DjangoIntegration()],
        send_default_pii=env.bool("SENTRY_SEND_DEFAULT_PII", default=False),  # noqa: F405
        enable_logs=env.bool("SENTRY_ENABLE_LOGS", default=True),  # noqa: F405
        traces_sample_rate=env.float("SENTRY_TRACES_SAMPLE_RATE", default=0.1),  # noqa: F405
        profile_session_sample_rate=env.float(  # noqa: F405
            "SENTRY_PROFILE_SESSION_SAMPLE_RATE",
            default=0.0,
        ),
        profile_lifecycle=env("SENTRY_PROFILE_LIFECYCLE", default="trace"),  # noqa: F405
    )

# ──────────────────────────────────────────────
# Logging — structured JSON
# ──────────────────────────────────────────────

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "()": "apps.core.journalisation.JsonFormatter",
            "datefmt": "%Y-%m-%dT%H:%M:%S%z",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "WARNING",
    },
    "loggers": {
        "django": {"level": "WARNING", "propagate": True},
        "apps": {"level": "INFO", "propagate": True},
    },
}
