"""Tout courriel adressé au secrétariat part en copie à la boîte de contact."""

import pytest
from django.core import mail

from apps.core.services.emails import envoyer_email, envoyer_maintenant, envoyer_notification_email


@pytest.fixture(autouse=True)
def _boites_reelles(settings):
    settings.ITEAG_COURRIEL_SECRETARIAT = "secretariat.iteag@gmail.com"
    settings.ITEAG_COURRIEL_COPIE = "contact.iteag@gmail.com"


def _envoyer(destinataires, **options):
    return envoyer_notification_email(
        sujet="Nouvelle candidature",
        titre="Nouvelle candidature",
        message="Un dossier attend.",
        destinataires=destinataires,
        differe=False,
        **options,
    )


@pytest.mark.django_db
class TestCopieSecretariat:
    def test_la_boite_de_contact_est_en_copie(self):
        assert _envoyer(["secretariat.iteag@gmail.com"])

        message = mail.outbox[0]
        assert message.to == ["secretariat.iteag@gmail.com"]
        assert message.cc == ["contact.iteag@gmail.com"]
        assert "contact.iteag@gmail.com" in message.recipients()

    def test_la_casse_de_l_adresse_ne_fait_pas_perdre_la_copie(self):
        assert _envoyer(["Secretariat.Iteag@Gmail.com"])

        assert mail.outbox[0].cc == ["contact.iteag@gmail.com"]

    def test_un_autre_destinataire_ne_declenche_aucune_copie(self):
        assert _envoyer(["etudiant@example.org"])

        assert mail.outbox[0].cc == []

    def test_un_envoi_confidentiel_n_est_jamais_copie(self):
        assert envoyer_email(
            sujet="Votre espace est ouvert",
            gabarit="core/emails/notification.html",
            contexte={"titre": "Lien", "message": "Lien personnel."},
            destinataires=["secretariat.iteag@gmail.com"],
            differe=False,
            confidentiel=True,
        )

        assert mail.outbox[0].cc == []

    def test_une_reponse_revient_au_secretariat(self):
        assert _envoyer(["etudiant@example.org"])

        assert mail.outbox[0].reply_to == ["secretariat.iteag@gmail.com"]

    def test_le_courriel_affiche_la_boite_reelle(self):
        assert _envoyer(["etudiant@example.org"])

        html = mail.outbox[0].alternatives[0].content
        assert "secretariat.iteag@gmail.com" in html
        assert "@iteag.org" not in html


@pytest.mark.django_db
class TestDestinatairesSansBoite:
    def test_une_adresse_iteag_est_refusee_avant_envoi(self):
        assert not _envoyer(["direction@iteag.org"])
        assert mail.outbox == []

    def test_un_lot_mixte_ne_garde_que_les_adresses_reelles(self):
        assert _envoyer(["direction@iteag.org", "etudiant@example.org"])

        assert mail.outbox[0].to == ["etudiant@example.org"]

    def test_une_ancienne_tache_celery_est_egalement_bloquee(self):
        assert not envoyer_maintenant(
            "Ancienne notification",
            "core/emails/notification.html",
            {"titre": "Test", "message": "Ancienne tâche."},
            ["direction@iteag.org"],
        )
        assert mail.outbox == []
