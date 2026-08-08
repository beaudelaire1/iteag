import pytest
from django.core.management import CommandError, call_command
from django.test import override_settings

from apps.core.services.production import anomalies_configuration_production


CONFIGURATION_PRODUCTION = {
    "DEBUG": False,
    "SECRET_KEY": "production-secret-" + "x" * 64,
    "SITE_URL": "https://iteag.org",
    "WAGTAILADMIN_BASE_URL": "https://iteag.org",
    "ALLOWED_HOSTS": ["iteag.org", "www.iteag.org"],
    "CSRF_TRUSTED_ORIGINS": ["https://iteag.org", "https://www.iteag.org"],
    "SECURE_SSL_REDIRECT": True,
    "SESSION_COOKIE_SECURE": True,
    "CSRF_COOKIE_SECURE": True,
    "SESSION_COOKIE_HTTPONLY": True,
    "SECURE_CONTENT_TYPE_NOSNIFF": True,
    "SECURE_HSTS_SECONDS": 31536000,
    "X_FRAME_OPTIONS": "DENY",
    "OTP_ENFORCE": True,
    "ROLES_2FA_OBLIGATOIRE": ["admin", "secretariat"],
    "EMAIL_BACKEND": "django.core.mail.backends.smtp.EmailBackend",
    "EMAIL_HOST": "smtp.example.test",
    "EMAIL_HOST_USER": "iteag",
    "EMAIL_HOST_PASSWORD": "secret",
    "DEFAULT_FROM_EMAIL": "secretariat@iteag.org",
    "SERVER_EMAIL": "errors@iteag.org",
    "CLOUDFLARE_TURNSTILE_ENABLED": True,
    "CLOUDFLARE_TURNSTILE_SITE_KEY": "site-key",
    "CLOUDFLARE_TURNSTILE_SECRET_KEY": "secret-key",
    "STORAGES": {"default": {"BACKEND": "storages.backends.s3boto3.S3Boto3Storage"}},
    "AWS_ACCESS_KEY_ID": "access",
    "AWS_SECRET_ACCESS_KEY": "secret",
    "AWS_STORAGE_BUCKET_NAME": "iteag-media",
    "AWS_S3_ENDPOINT_URL": "https://r2.example.test",
    "SENTRY_DSN": "https://public@example.test/1",
    "ELEARNING_DIFFUSION_VIDEO": "bunny",
    "BUNNY_ZONE_DIFFUSION": "https://video.example.test",
    "BUNNY_CLE_SIGNATURE": "video-secret",
    "DATABASES": {"default": {"ENGINE": "django.db.backends.postgresql"}},
    "CACHES": {"default": {"BACKEND": "django_redis.cache.RedisCache"}},
    "CELERY_BROKER_URL": "redis://redis:6379/1",
    "CELERY_RESULT_BACKEND": "redis://redis:6379/2",
}


@override_settings(**CONFIGURATION_PRODUCTION)
def test_configuration_complete_est_prete():
    assert anomalies_configuration_production() == []


@override_settings(
    **{
        **CONFIGURATION_PRODUCTION,
        "EMAIL_BACKEND": "django.core.mail.backends.console.EmailBackend",
        "CLOUDFLARE_TURNSTILE_ENABLED": False,
        "SENTRY_DSN": "",
    }
)
def test_les_replis_de_developpement_sont_refuses():
    anomalies = anomalies_configuration_production()

    assert any("EMAIL_BACKEND" in anomalie for anomalie in anomalies)
    assert any("Turnstile" in anomalie for anomalie in anomalies)
    assert any("SENTRY_DSN" in anomalie for anomalie in anomalies)


@override_settings(
    **{
        **CONFIGURATION_PRODUCTION,
        "ALLOWED_HOSTS": ["*"],
        "SITE_URL": "http://iteag.org",
        "WAGTAILADMIN_BASE_URL": "http://iteag.org",
        "CSRF_TRUSTED_ORIGINS": [],
    }
)
def test_une_origine_non_securisee_est_refusee():
    anomalies = anomalies_configuration_production()

    assert any("HTTPS" in anomalie for anomalie in anomalies)
    assert any("'*'" in anomalie for anomalie in anomalies)
    assert any("CSRF_TRUSTED_ORIGINS" in anomalie for anomalie in anomalies)


@override_settings(**CONFIGURATION_PRODUCTION)
def test_la_commande_reussit_sur_une_configuration_complete(capsys):
    call_command("verifier_production")
    assert "Configuration production : OK" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("nom", "valeur"),
    [
        ("AWS_S3_ENDPOINT_URL", ""),
        ("BUNNY_CLE_SIGNATURE", ""),
        ("EMAIL_HOST_PASSWORD", ""),
    ],
)
def test_la_commande_echoue_si_un_secret_fonctionnel_manque(settings, nom, valeur):
    for cle, config in CONFIGURATION_PRODUCTION.items():
        setattr(settings, cle, config)
    setattr(settings, nom, valeur)

    with pytest.raises(CommandError):
        call_command("verifier_production")
