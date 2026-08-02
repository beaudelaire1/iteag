"""Une notification traitée doit pouvoir quitter la liste.

Marquer lu ne suffisait pas : l'avis restait à l'écran et repoussait les
suivants. La suppression ne porte que sur l'avis — jamais sur le dossier, la
copie ou la commande qu'il annonçait.
"""

import pytest
from django.urls import reverse

from apps.accounts.models import User
from apps.core.models import Notification
from apps.core.services.notifications import notifier

pytestmark = pytest.mark.django_db

MOT_DE_PASSE = "motdepasse-long-12"


@pytest.fixture
def etudiant(db):
    return User.objects.create_user(
        username="jdupont", email="jdupont@iteag.org", password=MOT_DE_PASSE, role=User.Role.ETUDIANT
    )


@pytest.fixture
def autre(db):
    return User.objects.create_user(
        username="autre", email="autre@iteag.org", password=MOT_DE_PASSE, role=User.Role.ETUDIANT
    )


def test_le_destinataire_supprime_sa_notification(client, etudiant):
    avis = notifier(etudiant, "Votre relevé est disponible")
    client.force_login(etudiant)

    reponse = client.post(reverse("core:notification_supprimer", args=[avis.pk]))

    assert reponse.status_code == 302
    assert not Notification.objects.filter(pk=avis.pk).exists()


def test_on_ne_supprime_pas_l_avis_d_un_autre(client, etudiant, autre):
    """L'identifiant est devinable : seul le destinataire fait autorité."""
    avis = notifier(autre, "Sa note à lui")
    client.force_login(etudiant)

    reponse = client.post(reverse("core:notification_supprimer", args=[avis.pk]))

    assert reponse.status_code == 404
    assert Notification.objects.filter(pk=avis.pk).exists()


def test_la_suppression_exige_un_post(client, etudiant):
    avis = notifier(etudiant, "Annonce")
    client.force_login(etudiant)
    assert client.get(reverse("core:notification_supprimer", args=[avis.pk])).status_code == 405
    assert Notification.objects.filter(pk=avis.pk).exists()


def test_un_visiteur_anonyme_ne_supprime_rien(client, etudiant):
    avis = notifier(etudiant, "Annonce")
    reponse = client.post(reverse("core:notification_supprimer", args=[avis.pk]))
    assert reponse.status_code == 302
    assert reverse("accounts:login") in reponse.url
    assert Notification.objects.filter(pk=avis.pk).exists()


def test_le_vidage_epargne_les_non_lues(client, etudiant):
    """Effacer en bloc ce qu'on n'a pas encore vu ferait perdre l'information."""
    lue = notifier(etudiant, "Déjà traitée")
    lue.marquer_lue()
    non_lue = notifier(etudiant, "Pas encore vue")

    client.force_login(etudiant)
    client.post(reverse("core:notifications_supprimer_lues"))

    assert not Notification.objects.filter(pk=lue.pk).exists()
    assert Notification.objects.filter(pk=non_lue.pk).exists()


def test_le_vidage_ne_touche_que_ses_propres_avis(client, etudiant, autre):
    sien = notifier(etudiant, "À moi")
    sien.marquer_lue()
    celui_de_l_autre = notifier(autre, "À lui")
    celui_de_l_autre.marquer_lue()

    client.force_login(etudiant)
    client.post(reverse("core:notifications_supprimer_lues"))

    assert not Notification.objects.filter(pk=sien.pk).exists()
    assert Notification.objects.filter(pk=celui_de_l_autre.pk).exists()


def test_la_liste_propose_la_suppression(client, etudiant):
    avis = notifier(etudiant, "Annonce")
    client.force_login(etudiant)
    contenu = client.get(reverse("core:notifications")).content.decode()
    assert reverse("core:notification_supprimer", args=[avis.pk]) in contenu
    assert reverse("core:notifications_supprimer_lues") in contenu
