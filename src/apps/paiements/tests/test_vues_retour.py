"""
Ce que montrent les pages de retour de paiement, et à qui.

Le retour Stripe reste privé et peut réconcilier immédiatement une session
payée lorsque le webhook n'est pas encore arrivé.
"""

from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

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


def test_le_retour_confirme_un_paiement_avant_le_webhook(client, reglement, monkeypatch):
    """Une carte immédiatement payée ne doit jamais rester en attente du webhook."""
    client.force_login(reglement.utilisateur)

    monkeypatch.setattr(
        "apps.paiements.views.recuperer_session_checkout",
        lambda session_id: {
            "id": session_id,
            "client_reference_id": str(reglement.pk),
            "payment_status": "paid",
            "amount_total": reglement.montant_en_centimes,
            "payment_intent": "pi_test_retour",
        },
    )

    reponse = client.get(
        reverse("paiements:succes", kwargs={"pk": reglement.pk}),
        {"session_id": reglement.session_stripe},
    )

    reglement.refresh_from_db()
    assert reponse.status_code == 200
    assert reglement.statut == Reglement.Statut.PAYE
    assert reglement.contrepartie_delivree is True
    assert "Paiement confirmé" in reponse.content.decode()


def test_un_paiement_encaisse_sans_contrepartie_ne_promet_pas_l_acces(client, reglement):
    """
    Le pire écran possible : « Paiement confirmé » suivi d'un bouton qui mène
    à un 403. Tant que la contrepartie n'est pas ouverte, la page doit le dire
    et donner la référence à citer, pas proposer une porte fermée.
    """
    client.force_login(reglement.utilisateur)
    Reglement.objects.filter(pk=reglement.pk).update(
        statut=Reglement.Statut.PAYE,
        date_paiement=timezone.now(),
        contrepartie_delivree=False,
    )

    contenu = client.get(reverse("paiements:succes", kwargs={"pk": reglement.pk})).content.decode()

    assert "Commencer la formation" not in contenu
    assert "accès en cours d'ouverture" in contenu.lower()
    assert str(reglement.pk) in contenu
