"""Les deux documents que la loi impose de publier.

Ces pages ne sont pas éditoriales : elles sont servies par du code, référencées
dans le plan du site et liées depuis toutes les pages. Un test les tient à ce
contrat, parce qu'une page légale qui disparaît ne provoque aucune erreur
visible — c'est précisément ce qui la rend facile à perdre.
"""

import re

import pytest
from django.test import override_settings
from django.urls import reverse
from django.utils.html import strip_tags

from apps.core.services.production import anomalies_configuration_production


def texte_visible(reponse) -> str:
    """Le texte lu par un humain : sans balises, sans coupures de ligne."""
    return re.sub(r"\s+", " ", strip_tags(reponse.content.decode()))


@pytest.mark.django_db
class TestLesPagesLegalesSontPubliques:
    @pytest.mark.parametrize(
        "route",
        ["website:mentions_legales", "website:conditions_generales_vente"],
    )
    def test_la_page_repond_sans_compte(self, client, route):
        reponse = client.get(reverse(route))
        assert reponse.status_code == 200

    def test_les_mentions_identifient_l_editeur_et_l_hebergeur(self, client):
        contenu = client.get(reverse("website:mentions_legales")).content.decode()

        assert "Institut de Théologie Évangélique des Antilles et de la Guyane" in contenu
        assert "97139 Les Abymes" in contenu
        assert "Directeur de la publication" in contenu
        assert "Hébergement" in contenu

    @override_settings(
        ITEAG_FORME_JURIDIQUE="Association déclarée loi 1901",
        ITEAG_IMMATRICULATION="W9A1234567",
        ITEAG_DIRECTEUR_PUBLICATION="Prénom Nom",
        ITEAG_HEBERGEUR="Hébergeur Test",
        ITEAG_HEBERGEUR_ADRESSE="1 rue de l'Exemple, 97139 Les Abymes",
    )
    def test_les_valeurs_saisies_apparaissent_reellement(self, client):
        """Une donnée configurée mais non rendue laisserait la page incomplète en silence."""
        contenu = client.get(reverse("website:mentions_legales")).content.decode()

        for attendu in (
            "Association déclarée loi 1901",
            "W9A1234567",
            "Prénom Nom",
            "Hébergeur Test",
            "1 rue de l&#x27;Exemple, 97139 Les Abymes",
        ):
            assert attendu in contenu

    def test_les_cgv_couvrent_les_obligations_de_vente_a_distance(self, client):
        # Le texte rendu, débarrassé de son balisage : une expression coupée par
        # un retour à la ligne ou entourée d'un <strong> reste la même phrase
        # pour qui lit la page.
        contenu = texte_visible(client.get(reverse("website:conditions_generales_vente")))

        for attendu in (
            "Droit de rétractation",
            "quatorze jours",
            "garantie légale de conformité",
            "vices cachés",
            "médiation",
            "formulaire de rétractation",
        ):
            assert attendu.lower() in contenu.lower(), attendu

    @override_settings(
        ITEAG_MEDIATEUR="Médiation Exemple",
        ITEAG_MEDIATEUR_URL="https://mediation.example.test",
    )
    def test_le_mediateur_est_publie_quand_il_est_designe(self, client):
        contenu = client.get(reverse("website:conditions_generales_vente")).content.decode()

        assert "Médiation Exemple" in contenu
        assert "https://mediation.example.test" in contenu

    @override_settings(ITEAG_MEDIATEUR="")
    def test_aucun_mediateur_n_est_invente_faute_de_designation(self, client):
        """Mieux vaut une section absente qu'un médiateur qui n'existe pas."""
        contenu = client.get(reverse("website:conditions_generales_vente")).content.decode()

        assert "médiateur de la consommation dont relève" not in contenu


@pytest.mark.django_db
class TestLesPagesLegalesSontAtteignables:
    def test_le_pied_de_page_lie_les_deux_documents(self, client):
        """Une page légale que rien ne lie n'est pas « publiée » au sens utile."""
        contenu = client.get("/connexion/").content.decode()

        assert reverse("website:mentions_legales") in contenu
        assert reverse("website:conditions_generales_vente") in contenu

    def test_le_plan_du_site_les_recense(self, client):
        contenu = client.get("/sitemap.xml").content.decode()

        assert reverse("website:mentions_legales") in contenu
        assert reverse("website:conditions_generales_vente") in contenu

    def test_la_case_de_commande_lie_le_document_accepte(self):
        """« J'accepte les conditions de vente » doit pouvoir mener au texte accepté."""
        from apps.commerce.forms import CommandeForm

        libelle = str(CommandeForm().fields["accepte_conditions"].label)

        assert reverse("website:conditions_generales_vente") in libelle
        assert "conditions générales de vente" in libelle


@pytest.mark.django_db
class TestLeContratDeProductionExigeLesMentions:
    def test_une_instance_sans_identite_editoriale_est_refusee(self, settings):
        settings.ITEAG_FORME_JURIDIQUE = ""
        settings.ITEAG_IMMATRICULATION = ""
        settings.ITEAG_DIRECTEUR_PUBLICATION = ""
        settings.ITEAG_MEDIATEUR = ""

        anomalies = anomalies_configuration_production()

        for nom in (
            "ITEAG_FORME_JURIDIQUE",
            "ITEAG_IMMATRICULATION",
            "ITEAG_DIRECTEUR_PUBLICATION",
            "ITEAG_MEDIATEUR",
        ):
            assert any(nom in anomalie for anomalie in anomalies), nom
