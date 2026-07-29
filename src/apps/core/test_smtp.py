"""Contrôles de configuration du transport des notifications."""

from django.test import override_settings

from apps.core.checks import configuration_smtp


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend",
    EMAIL_HOST="",
    EMAIL_HOST_USER="",
    EMAIL_HOST_PASSWORD="",
)
def test_un_smtp_incomplet_est_signale():
    problemes = configuration_smtp(None)
    assert [probleme.id for probleme in problemes] == ["core.E004"]


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend",
    EMAIL_HOST="smtp.example.org",
    EMAIL_HOST_USER="notifications@example.org",
    EMAIL_HOST_PASSWORD="secret",
    EMAIL_USE_TLS=True,
    EMAIL_USE_SSL=False,
)
def test_un_smtp_complet_est_accepte():
    assert configuration_smtp(None) == []


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend",
    EMAIL_HOST="smtp.example.org",
    EMAIL_HOST_USER="notifications@example.org",
    EMAIL_HOST_PASSWORD="secret",
    EMAIL_USE_TLS=True,
    EMAIL_USE_SSL=True,
)
def test_tls_et_ssl_ne_sont_pas_actives_ensemble():
    problemes = configuration_smtp(None)
    assert [probleme.id for probleme in problemes] == ["core.E005"]
