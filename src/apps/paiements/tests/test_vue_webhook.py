"""
La vue webhook — une adresse publique qui déclenche des octrois.

C'est la surface la plus exposée du système : elle est accessible sans compte,
sans jeton CSRF, et son effet est d'ouvrir des accès payants. Ce qui la protège
est la signature Stripe, et rien d'autre. Ces tests vérifient qu'aucun chemin
ne contourne cette vérification, et que le code de réponse dit la vérité —
puisque c'est lui qui décide si Stripe redélivre ou abandonne.
"""

import json
from unittest.mock import patch

import pytest
from django.test import Client
from django.urls import reverse

from apps.elearning.models import InscriptionModule
from apps.paiements.models import Reglement
from apps.paiements.tests.conftest import evenement


def poster(client, corps, signature="sig_valide"):
    return client.post(
        reverse("paiements:webhook_stripe"),
        data=json.dumps(corps),
        content_type="application/json",
        HTTP_STRIPE_SIGNATURE=signature,
    )


@pytest.mark.django_db
class TestLaSignatureEstLeSeulLaissezPasser:
    def test_sans_signature_rien_n_est_traite(self, client, reglement, etudiant, module_vendu):
        reponse = client.post(
            reverse("paiements:webhook_stripe"),
            data=json.dumps({"id": "evt_1", "type": "checkout.session.completed"}),
            content_type="application/json",
        )
        assert reponse.status_code == 400
        assert InscriptionModule.objects.filter(etudiant=etudiant, module=module_vendu).exists() is False

    def test_une_signature_invalide_n_ouvre_aucun_acces(self, client, reglement, etudiant, module_vendu):
        """
        Le scénario à empêcher : quelqu'un poste « paiement abouti » sur une
        adresse publique et repart avec la formation.
        """
        with patch("apps.paiements.views.lire_evenement", side_effect=ValueError("signature")):
            reponse = poster(
                client,
                {
                    "id": "evt_forge",
                    "type": "checkout.session.completed",
                    "data": {"object": {"client_reference_id": str(reglement.pk)}},
                },
            )
        assert reponse.status_code == 400
        reglement.refresh_from_db()
        assert reglement.statut == Reglement.Statut.EN_ATTENTE
        assert InscriptionModule.objects.filter(etudiant=etudiant, module=module_vendu).exists() is False

    def test_une_signature_valide_est_traitee(self, client, reglement, etudiant, module_vendu):
        charge = evenement(
            "checkout.session.completed",
            {
                "id": reglement.session_stripe,
                "client_reference_id": str(reglement.pk),
                "payment_status": "paid",
                "payment_intent": "pi_1",
                "amount_total": reglement.montant_en_centimes,
            },
        )
        with patch("apps.paiements.views.lire_evenement", return_value=charge):
            reponse = poster(client, charge)
        assert reponse.status_code == 200
        assert InscriptionModule.objects.filter(etudiant=etudiant, module=module_vendu).exists() is True


@pytest.mark.django_db
class TestLeCodeDeReponseNeMentPas:
    """
    Répondre 200 signifie « ne renvoyez plus ». Le renvoyer sur un échec ferait
    perdre l'encaissement définitivement.
    """

    def test_un_echec_de_traitement_renvoie_500(self, client, reglement):
        charge = evenement("checkout.session.completed", {"client_reference_id": str(reglement.pk)})
        with (
            patch("apps.paiements.views.lire_evenement", return_value=charge),
            patch("apps.paiements.services.webhook.traiter", side_effect=RuntimeError("base indisponible")),
        ):
            reponse = poster(client, charge)
        assert reponse.status_code == 500

    def test_une_redelivrance_est_acquittee_sans_retraitement(self, client, reglement):
        charge = evenement(
            "checkout.session.completed",
            {
                "id": reglement.session_stripe,
                "client_reference_id": str(reglement.pk),
                "payment_status": "paid",
                "amount_total": reglement.montant_en_centimes,
            },
        )
        with patch("apps.paiements.views.lire_evenement", return_value=charge):
            assert poster(client, charge).status_code == 200
            assert poster(client, charge).status_code == 200

    def test_stripe_non_configure_renvoie_503(self, client, settings):
        """Ni 200 — qui perdrait l'événement — ni 500 muet : un état de service."""
        settings.STRIPE_CLE_SECRETE = ""
        settings.STRIPE_SECRET_WEBHOOK = ""
        reponse = poster(client, {"id": "evt_1", "type": "checkout.session.completed"})
        assert reponse.status_code == 503


# Un module s'ouvre dès l'encaissement : l'achat n'est accepté qu'accompagné de
# la renonciation expresse au droit de rétractation (art. L221-28 du code de la
# consommation). Les parcours nominaux ci-dessous la portent donc toujours.
ACHAT_CONFORME = {"renonce_retractation": "1"}


@pytest.mark.django_db
class TestLeParcoursDAchat:
    def test_l_achat_sans_renonciation_est_refuse(self, client, module_vendu, etudiant):
        """Sans renonciation expresse, un contenu déjà consultable resterait remboursable."""
        client.force_login(etudiant.utilisateur)
        reponse = client.post(reverse("paiements:acheter_module", args=[module_vendu.slug]))

        assert reponse.status_code == 302
        assert reponse.url == module_vendu.get_absolute_url()
        assert Reglement.objects.count() == 0

    def test_la_case_de_renonciation_est_presentee_avant_l_achat(self, client, module_vendu, etudiant):
        """La déclaration doit être proposée à l'écran, pas seulement exigée côté serveur."""
        client.force_login(etudiant.utilisateur)
        contenu = client.get(module_vendu.get_absolute_url()).content.decode()

        assert 'name="renonce_retractation"' in contenu
        assert reverse("website:conditions_generales_vente") in contenu

    def test_l_achat_exige_d_etre_connecte(self, client, module_vendu):
        reponse = client.post(reverse("paiements:acheter_module", args=[module_vendu.slug]))
        assert reponse.status_code == 302
        assert "/connexion" in reponse.url or "login" in reponse.url

    def test_le_get_n_ouvre_pas_de_session_de_paiement(self, client, module_vendu, etudiant):
        """Un lien préchargé par le navigateur ne doit pas créer de règlement."""
        client.force_login(etudiant.utilisateur)
        reponse = client.get(reverse("paiements:acheter_module", args=[module_vendu.slug]))
        assert reponse.status_code == 405
        assert Reglement.objects.count() == 0

    def test_un_module_gratuit_ne_s_achete_pas(self, client, module_vendu, etudiant):
        module_vendu.politique_acces = module_vendu.PolitiqueAcces.SUR_OCTROI
        module_vendu.save(update_fields=["politique_acces"])
        client.force_login(etudiant.utilisateur)
        client.post(reverse("paiements:acheter_module", args=[module_vendu.slug]), ACHAT_CONFORME)
        assert Reglement.objects.count() == 0

    def test_le_prix_vient_de_la_base_pas_de_la_requete(self, client, module_vendu, etudiant):
        """Un montant qui transiterait par le navigateur serait négociable."""
        client.force_login(etudiant.utilisateur)
        client.post(
            reverse("paiements:acheter_module", args=[module_vendu.slug]),
            {**ACHAT_CONFORME, "montant_ttc": "1.00", "prix": "1"},
        )
        reglement = Reglement.objects.get()
        assert reglement.montant_ttc == module_vendu.prix_ttc

    def test_deux_clics_ne_creent_qu_un_reglement(self, client, module_vendu, etudiant):
        client.force_login(etudiant.utilisateur)
        adresse = reverse("paiements:acheter_module", args=[module_vendu.slug])
        client.post(adresse, ACHAT_CONFORME)
        client.post(adresse, ACHAT_CONFORME)
        assert Reglement.objects.count() == 1

    def test_on_ne_rachete_pas_un_module_deja_acquis(self, client, module_vendu, etudiant):
        InscriptionModule.objects.create(
            etudiant=etudiant, module=module_vendu, statut=InscriptionModule.StatutAcces.ACTIF
        )
        client.force_login(etudiant.utilisateur)
        client.post(reverse("paiements:acheter_module", args=[module_vendu.slug]), ACHAT_CONFORME)
        assert Reglement.objects.count() == 0

    def test_le_paiement_reste_sur_une_page_iteag(self, client, module_vendu, etudiant):
        client.force_login(etudiant.utilisateur)
        ouverture = client.post(reverse("paiements:acheter_module", args=[module_vendu.slug]), ACHAT_CONFORME)
        reglement = Reglement.objects.get()

        assert ouverture.url == reverse("paiements:checkout", args=[reglement.pk])
        page = client.get(ouverture.url)
        contenu = page.content.decode()
        assert page.status_code == 200
        assert "Finaliser le paiement" in contenu
        assert "stripe-checkout" in contenu
        assert "120,00" in contenu or "120.00" in contenu

    def test_la_session_integree_est_creee_en_post(self, client, module_vendu, etudiant):
        client.force_login(etudiant.utilisateur)
        client.post(reverse("paiements:acheter_module", args=[module_vendu.slug]), ACHAT_CONFORME)
        reglement = Reglement.objects.get()

        with patch(
            "apps.paiements.views.creer_session_integree",
            return_value="cs_test_secret_exemple",
        ) as creer:
            reponse = client.post(reverse("paiements:session_checkout", args=[reglement.pk]))

        assert reponse.status_code == 200
        assert reponse.json() == {"client_secret": "cs_test_secret_exemple"}
        creer.assert_called_once()

    def test_un_autre_compte_ne_voit_pas_le_paiement(self, client, module_vendu, etudiant):
        client.force_login(etudiant.utilisateur)
        client.post(reverse("paiements:acheter_module", args=[module_vendu.slug]), ACHAT_CONFORME)
        reglement = Reglement.objects.get()
        client.logout()

        assert client.get(reverse("paiements:checkout", args=[reglement.pk])).status_code == 404
        assert client.post(reverse("paiements:session_checkout", args=[reglement.pk])).status_code == 404

    def test_la_creation_de_session_exige_un_jeton_csrf(self, reglement):
        navigateur = Client(enforce_csrf_checks=True)
        navigateur.force_login(reglement.utilisateur)

        reponse = navigateur.post(reverse("paiements:session_checkout", args=[reglement.pk]))

        assert reponse.status_code == 403
