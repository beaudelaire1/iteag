"""
Ce que montrent les pages de retour de paiement, et à qui.

Elles ne décident de rien, mais elles nomment le payeur, son courriel et ce
qu'il a réglé. Un tiers muni de l'identifiant du règlement y lisait tout : la
clé est un UUID, donc non énumérable, mais un lien recopié dans une
conversation ou repris d'un journal suffisait.
"""

from decimal import Decimal

import pytest
from django.urls import reverse

from apps.accounts.models import User
from apps.paiements.models import Reglement

pytestmark = pytest.mark.django_db

PAGES = ["paiements:succes", "paiements:annulation", "paiements:recu"]


@pytest.fixture
def reglement_anonyme(db, module_vendu):
    """Un achat engagé sans compte : le visiteur n'a laissé qu'un courriel."""
    return Reglement.objects.create(
        nature=Reglement.Nature.MODULE,
        module=module_vendu,
        email="visiteur@exemple.org",
        libelle=f"Formation — {module_vendu.titre}",
        montant_ttc=Decimal("120.00"),
        taux_tva=Decimal("0.00"),
    )


@pytest.fixture
def tiers(db):
    return User.objects.create_user(
        username="tiers_curieux",
        email="tiers@iteag.org",
        password="motdepasse-long-12",
        role=User.Role.ETUDIANT,
    )


@pytest.mark.parametrize("nom_route", PAGES)
def test_le_proprietaire_est_servi(client, reglement, nom_route):
    """Le retour de Stripe doit aboutir pour celui qui a payé."""
    client.force_login(reglement.utilisateur)
    assert client.get(reverse(nom_route, kwargs={"pk": reglement.pk})).status_code == 200


@pytest.mark.parametrize("nom_route", PAGES)
def test_un_tiers_connecte_ne_lit_pas_le_reglement_d_un_autre(client, reglement, tiers, nom_route):
    client.force_login(tiers)
    assert client.get(reverse(nom_route, kwargs={"pk": reglement.pk})).status_code == 404


@pytest.mark.parametrize("nom_route", PAGES)
def test_un_visiteur_anonyme_ne_lit_pas_le_reglement_d_un_compte(client, reglement, nom_route):
    assert client.get(reverse(nom_route, kwargs={"pk": reglement.pk})).status_code == 404


@pytest.mark.parametrize("nom_route", PAGES)
def test_un_achat_sans_compte_reste_consultable_sans_compte(client, reglement_anonyme, nom_route):
    """Le cookie de session se perd, l'onglet change : le retour doit aboutir."""
    assert client.get(reverse(nom_route, kwargs={"pk": reglement_anonyme.pk})).status_code == 200
