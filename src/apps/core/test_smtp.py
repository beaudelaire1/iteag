"""Contrôles de configuration du transport des notifications."""

import smtplib
from unittest import mock

import pytest
from django.test import override_settings

from apps.core.checks import configuration_smtp
from apps.core.services.emails import (
    ErreurSMTPTemporaire,
    _est_erreur_smtp_temporaire,
    envoyer_maintenant,
)


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


@pytest.mark.parametrize(
    "erreur",
    [
        TimeoutError("The read operation timed out"),
        smtplib.SMTPServerDisconnected("Connection unexpectedly closed: timed out"),
        ConnectionResetError("Connection reset by peer"),
        BrokenPipeError("Broken pipe"),
    ],
)
def test_les_interruptions_reseau_smtp_sont_temporaires(erreur):
    assert _est_erreur_smtp_temporaire(erreur)


@pytest.mark.parametrize(
    "erreur",
    [
        TimeoutError("The read operation timed out"),
        smtplib.SMTPServerDisconnected("Connection unexpectedly closed: timed out"),
    ],
)
def test_le_worker_recoit_une_erreur_rejouable_pour_un_timeout(erreur):
    with mock.patch("apps.core.services.emails.EmailMultiAlternatives.send", side_effect=erreur):
        with pytest.raises(ErreurSMTPTemporaire, match=type(erreur).__name__):
            envoyer_maintenant(
                "Invitation",
                "core/emails/notification.html",
                {"titre": "Invitation", "message": "Votre compte est prêt."},
                ["destinataire@example.org"],
                propager_erreur_smtp_temporaire=True,
            )


def test_un_refus_smtp_permanent_ne_declenche_pas_de_relance():
    refus = smtplib.SMTPAuthenticationError(535, b"Bad credentials")
    with mock.patch("apps.core.services.emails.EmailMultiAlternatives.send", side_effect=refus):
        assert not envoyer_maintenant(
            "Invitation",
            "core/emails/notification.html",
            {"titre": "Invitation", "message": "Votre compte est prêt."},
            ["destinataire@example.org"],
            propager_erreur_smtp_temporaire=True,
        )
