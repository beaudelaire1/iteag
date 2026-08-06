"""Contrôles du paiement au démarrage."""

import pytest

from apps.paiements.checks import configuration_stripe, structure_paiements


def test_relation_inscription_chargee_avant_les_requetes():
    """Le checkout doit pouvoir utiliser select_related('inscription_associee')."""
    assert structure_paiements(None) == []


@pytest.mark.parametrize(
    ("autoriser", "identifiant"),
    [(False, "paiements.E003"), (True, "paiements.W002")],
)
def test_cle_de_test_hors_debug(settings, autoriser, identifiant):
    """Le blocage n'est levé que par l'opt-in explicite de recette."""
    settings.DEBUG = False
    settings.STRIPE_CLE_SECRETE = "sk_test_abc"
    settings.STRIPE_SECRET_WEBHOOK = "whsec_abc"
    settings.STRIPE_CLE_PUBLIABLE = "pk_test_abc"
    settings.PAIEMENTS_AUTORISER_CLES_TEST = autoriser

    anomalies = configuration_stripe(None)

    assert [a.id for a in anomalies] == [identifiant]


def test_cle_live_ne_declenche_rien(settings):
    settings.DEBUG = False
    settings.STRIPE_CLE_SECRETE = "sk_live_abc"
    settings.STRIPE_SECRET_WEBHOOK = "whsec_abc"
    settings.STRIPE_CLE_PUBLIABLE = "pk_live_abc"
    settings.PAIEMENTS_AUTORISER_CLES_TEST = False

    assert configuration_stripe(None) == []
