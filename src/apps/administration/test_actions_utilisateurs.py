import pytest
from django.core import mail
from django.urls import reverse

from apps.accounts.models import User
from apps.administration.services.comptes import (
    envoyer_reinitialisation_mot_de_passe,
    renvoyer_invitation_utilisateur,
)

pytestmark = pytest.mark.django_db


def test_renvoi_invitation_envoie_un_lien_personnel(settings):
    settings.SITE_URL = "https://iteag.org"
    compte = User.objects.create_user(
        username="invitation.test",
        email="invitation@example.org",
        password="motdepasse-long-12",
        first_name="Jean",
        role=User.Role.ETUDIANT,
    )

    assert renvoyer_invitation_utilisateur(compte) is True
    assert len(mail.outbox) == 1
    message = mail.outbox[0]
    assert message.to == ["invitation@example.org"]
    assert "Votre accès ITEAG" in message.subject
    assert "/mot-de-passe/confirmer/" in message.body


def test_reinitialisation_envoie_un_lien_sans_changer_le_mot_de_passe(settings):
    settings.SITE_URL = "https://iteag.org"
    compte = User.objects.create_user(
        username="reset.test",
        email="reset@example.org",
        password="motdepasse-long-12",
        first_name="Rose",
        role=User.Role.ETUDIANT,
    )

    assert envoyer_reinitialisation_mot_de_passe(compte) is True
    compte.refresh_from_db()

    assert compte.check_password("motdepasse-long-12")
    assert len(mail.outbox) == 1
    assert "/mot-de-passe/confirmer/" in mail.outbox[0].body
    assert "reste valable" in mail.outbox[0].body


def test_reinitialisation_fonctionne_aussi_pour_un_compte_sans_mot_de_passe_utilisable(settings):
    settings.SITE_URL = "https://iteag.org"
    compte = User.objects.create_user(
        username="premiere.connexion",
        email="premiere@example.org",
        password="temporaire-long-12",
        role=User.Role.ETUDIANT,
    )
    compte.set_unusable_password()
    compte.save(update_fields=["password"])

    assert envoyer_reinitialisation_mot_de_passe(compte) is True
    assert "/mot-de-passe/confirmer/" in mail.outbox[0].body


def test_aucun_email_n_est_envoye_pour_un_compte_inactif():
    compte = User.objects.create_user(
        username="inactif",
        email="inactif@example.org",
        password="motdepasse-long-12",
        role=User.Role.ETUDIANT,
        is_active=False,
    )

    assert renvoyer_invitation_utilisateur(compte) is False
    assert envoyer_reinitialisation_mot_de_passe(compte) is False
    assert mail.outbox == []


def test_un_non_superutilisateur_ne_peut_pas_agir_sur_un_superutilisateur(client):
    secretaire = User.objects.create_user(
        username="secretaire_actions",
        email="secretaire@example.org",
        password="motdepasse-long-12",
        role=User.Role.SECRETARIAT,
    )
    superutilisateur = User.objects.create_superuser(
        username="super_actions",
        email="super@example.org",
        password="motdepasse-long-12",
    )

    client.force_login(secretaire)
    reponse = client.post(
        reverse("administration:user_action", args=[superutilisateur.pk]),
        {"action": "basculer_actif"},
    )

    assert reponse.status_code == 302
    superutilisateur.refresh_from_db()
    assert superutilisateur.is_active is True
