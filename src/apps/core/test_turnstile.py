import logging
from unittest.mock import Mock, patch

import pytest
from django.test import RequestFactory, override_settings
from django.urls import reverse
from requests.exceptions import Timeout

from apps.core.checks import configuration_turnstile
from apps.core.services.turnstile import MESSAGE_ECHEC, valider_requete

PROTECTION_ACTIVE = {
    "CLOUDFLARE_TURNSTILE_ENABLED": True,
    "CLOUDFLARE_TURNSTILE_SITE_KEY": "site-key-test",
    "CLOUDFLARE_TURNSTILE_SECRET_KEY": "secret-key-test",
    "CLOUDFLARE_TURNSTILE_TIMEOUT": 3.0,
    "ALLOWED_HOSTS": ["iteag.org", "testserver"],
}


def requete_avec_jeton():
    return RequestFactory().post(
        "/protection/",
        {"cf-turnstile-response": "jeton-valide"},
        HTTP_HOST="iteag.org",
        HTTP_CF_CONNECTING_IP="203.0.113.10",
    )


@override_settings(**PROTECTION_ACTIVE)
@patch("apps.core.services.turnstile.requests.post")
def test_siteverify_valide_action_hote_et_ip(post):
    reponse = Mock()
    reponse.json.return_value = {
        "success": True,
        "action": "connexion",
        "hostname": "iteag.org",
        "error-codes": [],
    }
    post.return_value = reponse

    assert valider_requete(requete_avec_jeton(), action="connexion") is True
    donnees = post.call_args.kwargs["data"]
    assert donnees["secret"] == "secret-key-test"
    assert donnees["response"] == "jeton-valide"
    assert donnees["remoteip"] == "203.0.113.10"
    assert donnees["idempotency_key"]
    assert post.call_args.kwargs["timeout"] == 3.0


@override_settings(**PROTECTION_ACTIVE)
@patch("apps.core.services.turnstile.requests.post")
def test_un_jeton_absent_est_refuse_sans_appel_reseau(post):
    requete = RequestFactory().post("/protection/", HTTP_HOST="iteag.org")
    assert valider_requete(requete, action="connexion") is False
    post.assert_not_called()


@override_settings(**PROTECTION_ACTIVE)
@pytest.mark.parametrize(
    ("action", "hostname"),
    [("contact", "iteag.org"), ("connexion", "pirate.example")],
)
@patch("apps.core.services.turnstile.requests.post")
def test_action_ou_hote_inattendu_est_refuse(post, action, hostname):
    reponse = Mock()
    reponse.json.return_value = {
        "success": True,
        "action": action,
        "hostname": hostname,
        "error-codes": [],
    }
    post.return_value = reponse

    assert valider_requete(requete_avec_jeton(), action="connexion") is False


@override_settings(**PROTECTION_ACTIVE)
@patch("apps.core.services.turnstile.requests.post", side_effect=Timeout)
def test_indisponibilite_cloudflare_echoue_fermee(post):
    assert valider_requete(requete_avec_jeton(), action="connexion") is False
    assert post.call_count == 2


@override_settings(**PROTECTION_ACTIVE)
@patch("apps.core.services.turnstile.requests.post")
def test_un_timeout_transitoire_est_retente_avec_la_meme_idempotence(post):
    reponse = Mock()
    reponse.json.return_value = {
        "success": True,
        "action": "connexion",
        "hostname": "iteag.org",
        "error-codes": [],
    }
    post.side_effect = [Timeout, reponse]

    assert valider_requete(requete_avec_jeton(), action="connexion") is True
    assert post.call_count == 2
    assert (
        post.call_args_list[0].kwargs["data"]["idempotency_key"]
        == post.call_args_list[1].kwargs["data"]["idempotency_key"]
    )


# Les deux refus ci-dessous se ressemblent — même retour `False`, même message
# à l'écran — et n'appellent pas du tout la même réaction : un jeton rejeté est
# un visiteur qui recommence, une panne de Siteverify bloque toutes les
# connexions, personnel compris. Le §5 du runbook fait chercher ces deux
# libellés dans le journal pour trancher : les figer ici évite qu'un
# remaniement les change sans que la procédure suive.


@override_settings(**PROTECTION_ACTIVE)
@patch("apps.core.services.turnstile.requests.post", side_effect=Timeout)
def test_une_panne_de_siteverify_se_distingue_dans_le_journal(post, caplog):
    with caplog.at_level(logging.INFO, logger="apps.core.services.turnstile"):
        valider_requete(requete_avec_jeton(), action="connexion")

    trace = caplog.records[-1]
    assert "Vérification Turnstile impossible" in trace.getMessage()
    assert trace.levelno == logging.WARNING
    assert trace.exc_info is None


@override_settings(**PROTECTION_ACTIVE)
@patch("apps.core.services.turnstile.requests.post")
def test_un_jeton_rejete_se_distingue_d_une_panne(post, caplog):
    reponse = Mock()
    reponse.json.return_value = {"success": False, "error-codes": ["invalid-input-response"]}
    post.return_value = reponse

    with caplog.at_level(logging.INFO, logger="apps.core.services.turnstile"):
        assert valider_requete(requete_avec_jeton(), action="connexion") is False

    trace = caplog.records[-1]
    assert "Jeton Turnstile refusé" in trace.getMessage()
    assert trace.levelno < logging.ERROR


@override_settings(CLOUDFLARE_TURNSTILE_ENABLED=False)
@patch("apps.core.services.turnstile.requests.post")
def test_protection_desactivee_ne_contacte_pas_cloudflare(post):
    assert valider_requete(RequestFactory().post("/"), action="connexion") is True
    post.assert_not_called()


@override_settings(**PROTECTION_ACTIVE)
def test_connexion_affiche_le_widget_et_le_script(client):
    contenu = client.get(reverse("accounts:login")).content.decode()
    assert 'data-sitekey="site-key-test"' in contenu
    assert 'data-action="connexion"' in contenu
    assert "https://challenges.cloudflare.com/turnstile/v0/api.js" in contenu


@override_settings(**PROTECTION_ACTIVE)
@pytest.mark.django_db
def test_connexion_sans_jeton_est_bloquee_avant_authentification(client, user):
    reponse = client.post(
        reverse("accounts:login"),
        {"username": user.username, "password": "testpass123!"},
    )
    assert reponse.status_code == 200
    assert MESSAGE_ECHEC in reponse.content.decode()
    assert "_auth_user_id" not in client.session


@override_settings(
    CLOUDFLARE_TURNSTILE_ENABLED=True,
    CLOUDFLARE_TURNSTILE_SITE_KEY="",
    CLOUDFLARE_TURNSTILE_SECRET_KEY="",
)
def test_controle_de_demarrage_refuse_une_configuration_incomplete():
    erreurs = configuration_turnstile(None)
    assert [erreur.id for erreur in erreurs] == ["core.E002"]
