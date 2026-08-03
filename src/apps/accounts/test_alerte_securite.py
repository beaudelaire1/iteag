"""
Alerte de sécurité sur changement d'information sensible.

Détourner l'adresse électronique d'un compte, puis demander une
réinitialisation de mot de passe, est le chemin le plus court vers une prise de
compte. Ces cas fixent ce que le titulaire doit apprendre, et par quel canal.
"""

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from apps.core.models import Notification

User = get_user_model()

MOT_DE_PASSE = "MotDePasseSolide!2026"


def _compte(role=User.Role.ETUDIANT, username="titulaire", **extra):
    return User.objects.create_user(
        username=username,
        email=f"{username}@iteag.org",
        password=MOT_DE_PASSE,
        first_name="Jean",
        last_name="Dupont",
        role=role,
        **extra,
    )


def _coordonnees(**champs):
    base = {
        "first_name": "Jean",
        "last_name": "Dupont",
        "email": "titulaire@iteag.org",
        "phone": "",
        "adresse": "",
        "complement_adresse": "",
        "code_postal": "",
        "ville": "",
        "pays": "Guadeloupe",
    }
    return {**base, **champs}


@pytest.fixture
def _boite_vide():
    mail.outbox.clear()
    yield
    mail.outbox.clear()


def test_le_changement_de_telephone_est_annonce(client, db, _boite_vide, django_capture_on_commit_callbacks):
    utilisateur = _compte()
    client.force_login(utilisateur)

    with django_capture_on_commit_callbacks(execute=True):
        client.post(reverse("accounts:profil"), _coordonnees(phone="0690123456"))

    notification = Notification.objects.get(destinataire=utilisateur)
    assert notification.type_notification == Notification.Type.SECURITE
    assert notification.titre == "Votre numéro de téléphone a été modifié"
    assert "réinitialisez immédiatement votre mot de passe" in notification.message

    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == ["titulaire@iteag.org"]
    assert "Réinitialiser mon mot de passe" in mail.outbox[0].alternatives[0][0]


def test_le_changement_d_adresse_electronique_previent_aussi_l_ancienne(
    client, db, _boite_vide, django_capture_on_commit_callbacks
):
    """Sinon celui qui vient de se faire voler son compte n'apprend jamais rien."""
    utilisateur = _compte()
    client.force_login(utilisateur)

    with django_capture_on_commit_callbacks(execute=True):
        client.post(reverse("accounts:profil"), _coordonnees(email="pirate@ailleurs.test"))

    destinataires = {adresse for message in mail.outbox for adresse in message.to}
    assert destinataires == {"titulaire@iteag.org", "pirate@ailleurs.test"}
    # Un envoi par adresse : deux destinataires ne se découvrent pas l'un l'autre.
    assert all(len(message.to) == 1 for message in mail.outbox)


def test_une_modification_sans_changement_reel_n_alerte_personne(
    client, db, _boite_vide, django_capture_on_commit_callbacks
):
    """Renvoyer le formulaire à l'identique n'est pas un événement de sécurité."""
    utilisateur = _compte()
    client.force_login(utilisateur)

    with django_capture_on_commit_callbacks(execute=True):
        client.post(reverse("accounts:profil"), _coordonnees(first_name="Jean-Marc"))

    assert not Notification.objects.filter(destinataire=utilisateur).exists()
    assert mail.outbox == []


def test_plusieurs_champs_donnent_une_seule_alerte(client, db, _boite_vide, django_capture_on_commit_callbacks):
    utilisateur = _compte()
    client.force_login(utilisateur)

    with django_capture_on_commit_callbacks(execute=True):
        client.post(reverse("accounts:profil"), _coordonnees(phone="0690123456", ville="Les Abymes"))

    notification = Notification.objects.get(destinataire=utilisateur)
    assert notification.titre == "Vos informations de compte ont été modifiées"
    assert "Votre numéro de téléphone" in notification.message
    assert "Votre ville" in notification.message


def test_le_changement_de_mot_de_passe_est_annonce(client, db, _boite_vide, django_capture_on_commit_callbacks):
    utilisateur = _compte(User.Role.ENSEIGNANT)
    client.force_login(utilisateur)

    with django_capture_on_commit_callbacks(execute=True):
        client.post(
            reverse("accounts:profil"),
            {
                "changer_mot_de_passe": "1",
                "old_password": MOT_DE_PASSE,
                "new_password1": "AutreMotDePasse!2026",
                "new_password2": "AutreMotDePasse!2026",
            },
        )

    notification = Notification.objects.get(destinataire=utilisateur)
    assert notification.titre == "Votre mot de passe a été modifié"
    assert len(mail.outbox) == 1


def test_la_reinitialisation_aboutie_est_annoncee(client, db, _boite_vide, django_capture_on_commit_callbacks):
    utilisateur = _compte()
    url = reverse(
        "accounts:password_reset_confirm",
        kwargs={
            "uidb64": urlsafe_base64_encode(force_bytes(utilisateur.pk)),
            "token": default_token_generator.make_token(utilisateur),
        },
    )
    # La vue échange le jeton contre un jeton de session avant d'accepter le POST.
    cible = client.get(url, follow=True).redirect_chain[-1][0] if client.get(url).status_code == 302 else url

    with django_capture_on_commit_callbacks(execute=True):
        client.post(cible, {"new_password1": "AutreMotDePasse!2026", "new_password2": "AutreMotDePasse!2026"})

    assert Notification.objects.filter(destinataire=utilisateur, titre="Votre mot de passe a été modifié").exists()


def test_le_secretariat_qui_modifie_un_compte_alerte_son_titulaire(
    client, db, _boite_vide, django_capture_on_commit_callbacks
):
    """Le titulaire est le dernier informé d'un changement qu'il n'a pas fait."""
    titulaire = _compte()
    agent = _compte(User.Role.SECRETARIAT, username="secretariat")
    client.force_login(agent)

    with django_capture_on_commit_callbacks(execute=True):
        client.post(
            reverse("administration:user_update", kwargs={"pk": titulaire.pk}),
            {
                "username": titulaire.username,
                "first_name": "Jean",
                "last_name": "Dupont",
                "email": titulaire.email,
                "phone": "0690999999",
                "role": User.Role.ETUDIANT,
                "is_active": "on",
                "password1": "",
            },
        )

    notification = Notification.objects.get(destinataire=titulaire)
    assert notification.titre == "Votre numéro de téléphone a été modifié"
    assert "depuis l'administration de l'institut" in notification.message
