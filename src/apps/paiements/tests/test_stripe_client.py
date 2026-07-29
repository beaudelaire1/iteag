from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from apps.paiements.services.stripe_client import creer_session_integree


@pytest.mark.django_db
def test_la_session_stripe_integree_recoit_le_montant_du_reglement(reglement, rf):
    reglement.session_stripe = ""
    session = SimpleNamespace(
        id="cs_test_integree",
        client_secret="cs_test_secret",
    )
    client_stripe = Mock()
    client_stripe.checkout.Session.create.return_value = session
    requete = rf.get("/")

    with patch("apps.paiements.services.stripe_client._client", return_value=client_stripe):
        secret = creer_session_integree(reglement, requete)

    assert secret == "cs_test_secret"
    parametres = client_stripe.checkout.Session.create.call_args.kwargs
    assert parametres["ui_mode"] == "embedded"
    assert parametres["payment_method_types"] == ["card"]
    assert parametres["line_items"][0]["price_data"]["unit_amount"] == reglement.montant_en_centimes
    assert parametres["return_url"].endswith(f"/paiements/{reglement.pk}/succes/?session_id={{CHECKOUT_SESSION_ID}}")


@pytest.mark.django_db
def test_une_session_integree_ouverte_est_reutilisee(reglement, rf):
    session = SimpleNamespace(
        id=reglement.session_stripe,
        status="open",
        payment_status="unpaid",
        ui_mode="embedded",
        client_secret="cs_test_secret_existant",
    )
    client_stripe = Mock()
    client_stripe.checkout.Session.retrieve.return_value = session

    with patch("apps.paiements.services.stripe_client._client", return_value=client_stripe):
        secret = creer_session_integree(reglement, rf.get("/"))

    assert secret == "cs_test_secret_existant"
    client_stripe.checkout.Session.create.assert_not_called()
