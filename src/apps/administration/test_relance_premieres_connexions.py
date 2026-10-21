"""Envoi groupé contrôlé des invitations pour les comptes jamais connectés."""
from unittest.mock import patch

import pytest
from django.core import mail
from django.core.cache import cache
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.administration.tasks import relancer_invitations_premiere_connexion
from apps.core.models import JournalAudit

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def reinitialiser_protection_relances():
    from apps.administration.views import AdminUserRelanceView

    cache.delete(AdminUserRelanceView.CLE_ANTIDOUBLON)
    yield
    cache.delete(AdminUserRelanceView.CLE_ANTIDOUBLON)


@pytest.fixture
def personnel(client, settings):
    settings.SITE_URL = "https://iteag.org"
    user = User.objects.create_user(
        username="secretariat_relance",
        email="secretariat@example.org",
        password="motdepasse-long-12",
        role=User.Role.SECRETARIAT,
    )
    client.force_login(user)
    return user


@pytest.fixture
def comptes():
    exemples = [
        ("premiere_a", User.Role.ETUDIANT, True, False, "a@example.org"),
        ("premiere_b", User.Role.ENSEIGNANT, True, False, "b@example.org"),
        ("deja_connecte", User.Role.ETUDIANT, True, True, "c@example.org"),
        ("compte_inactif", User.Role.ETUDIANT, False, False, "d@example.org"),
        ("adresse_absente", User.Role.ETUDIANT, True, False, ""),
        ("domaine_interne", User.Role.ETUDIANT, True, False, "f@iteag.org"),
        ("adresse_invalide", User.Role.ETUDIANT, True, False, "email-invalide"),
        ("direction", User.Role.ADMIN, True, False, "direction@example.org"),
    ]
    resultat = {}
    for nom, role, actif, deja, email in exemples:
        compte = User.objects.create_user(
            username=nom,
            email=email,
            password="motdepasse-long-12",
            role=role,
            is_active=actif,
        )
        if deja:
            compte.last_login = timezone.now()
            compte.save(update_fields=["last_login"])
        resultat[nom] = compte
    resultat["super"] = User.objects.create_superuser(
        username="super_non_connecte",
        email="super@example.org",
        password="motdepasse-long-12",
    )
    return resultat


def test_bouton_et_cible_excluent_comptes_non_eligibles(client, personnel, comptes):
    reponse = client.get(reverse("administration:utilisateurs"))
    assert reponse.status_code == 200
    assert reponse.context["nombre_relances"] == 2
    assert "Renvoyer les invitations (2)" in reponse.content.decode()
    assert reverse("administration:user_relance_group") in reponse.content.decode()

    reponse = client.post(reverse("administration:user_relance_group"))
    assert reponse.status_code == 302
    assert len(mail.outbox) == 2
    assert {email.to[0] for email in mail.outbox} == {"a@example.org", "b@example.org"}
    assert all("mot-de-passe/confirmer/" in email.body for email in mail.outbox)
    assert JournalAudit.objects.filter(metadonnees__operation="relance_invitations_executee").exists()


def test_relance_respecte_tous_les_filtres_et_toutes_les_pages(client, personnel, comptes):
    for i in range(33):
        User.objects.create_user(
            username=f"cible_massive_{i}",
            email=f"cible_massive_{i}@example.org",
            password="motdepasse-long-12",
        )
    url = reverse("administration:utilisateurs")
    filtres = {"role": User.Role.ETUDIANT, "q": "cible_massive", "connexion": "jamais"}
    reponse = client.get(url, filtres)
    assert reponse.context["users"].paginator.num_pages == 2
    assert reponse.context["nombre_relances"] == 33
    reponse = client.post(reverse("administration:user_relance_group"), filtres)
    assert reponse.status_code == 302
    assert len(mail.outbox) == 33


def test_double_clic_n_entraine_pas_deux_campagnes(client, personnel, comptes):
    url = reverse("administration:user_relance_group")
    assert client.post(url).status_code == 302
    assert client.post(url).status_code == 302
    assert len(mail.outbox) == 2
    assert JournalAudit.objects.filter(metadonnees__operation="relance_invitations_programmee").count() == 1


def test_le_worker_verifie_encore_l_etat_des_comptes(personnel, comptes):
    # Les données ont changé entre le clic et le traitement de la file.
    comptes["premiere_a"].last_login = timezone.now()
    comptes["premiere_a"].save(update_fields=["last_login"])
    resultat = relancer_invitations_premiere_connexion(
        [comptes["premiere_a"].pk, comptes["premiere_b"].pk, comptes["compte_inactif"].pk],
        personnel.pk,
    )
    assert resultat == {"programmes": 1, "ignores": 2, "echecs": 0}
    assert [email.to[0] for email in mail.outbox] == ["b@example.org"]


def test_absence_de_cible_n_envoie_rien(client, personnel, comptes):
    reponse = client.post(reverse("administration:user_relance_group"), {"statut": "inactif"})
    assert reponse.status_code == 302
    assert mail.outbox == []


def test_seuls_les_personnels_autorises_peuvent_relancer(client, personnel, comptes):
    etudiant = comptes["premiere_a"]
    client.force_login(etudiant)
    reponse = client.post(reverse("administration:user_relance_group"))
    assert reponse.status_code in (302, 403)
    assert mail.outbox == []


@override_settings(CELERY_TASK_ALWAYS_EAGER=False)
def test_broker_indisponible_ne_declenche_pas_de_smtp_http(client, personnel, comptes):
    with patch("apps.administration.views.current_app.connection_for_write", side_effect=RuntimeError("redis down")):
        reponse = client.post(reverse("administration:user_relance_group"))
    assert reponse.status_code == 302
    assert mail.outbox == []
    assert not JournalAudit.objects.filter(metadonnees__operation="relance_invitations_programmee").exists()


def test_la_relance_refuse_une_requete_get(client, personnel):
    assert client.get(reverse("administration:user_relance_group")).status_code == 405


def test_le_filtre_sans_destinataires_desactive_le_bouton(client, personnel, comptes):
    reponse = client.get(reverse("administration:utilisateurs"), {"statut": "inactif"})
    assert reponse.context["nombre_relances"] == 0
    assert 'disabled aria-disabled="true"' in reponse.content.decode()


def test_un_echec_de_publication_libere_la_protection_antidoublon(client, personnel, comptes):
    url = reverse("administration:user_relance_group")
    with override_settings(CELERY_TASK_ALWAYS_EAGER=False):
        with patch("apps.administration.views.current_app.connection_for_write", side_effect=RuntimeError("redis down")):
            assert client.post(url).status_code == 302

    assert client.post(url).status_code == 302
    assert {email.to[0] for email in mail.outbox} == {"a@example.org", "b@example.org"}
