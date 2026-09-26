"""Contrôles de configuration du transport des notifications."""

import smtplib

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


def test_une_reponse_smtp_421_est_temporaire():
    from apps.core.services.emails import _est_erreur_smtp_temporaire

    erreur = smtplib.SMTPConnectError(421, b"4.4.5 Server busy, try again later.")
    assert _est_erreur_smtp_temporaire(erreur)


def test_une_erreur_smtp_5xx_n_est_pas_rejouee():
    from apps.core.services.emails import _est_erreur_smtp_temporaire

    erreur = smtplib.SMTPAuthenticationError(535, b"5.7.8 Bad credentials")
    assert not _est_erreur_smtp_temporaire(erreur)
