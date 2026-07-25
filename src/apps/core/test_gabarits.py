"""
Tests de fumée sur les gabarits partagés.

Ces pages n'étaient couvertes par aucun test. Elles le sont désormais au moins
sur deux points : elles rendent sans erreur, et elles ne réintroduisent pas de
dépendance JavaScript incompatible avec la politique de sécurité (ADR-003).
"""

import pytest
from django.urls import reverse

# Directives d'un framework qui exigerait 'unsafe-eval' dans script-src.
DIRECTIVES_INTERDITES = ["x-data", "x-show", "x-cloak", "x-init", "x-collapse", "x-transition"]


@pytest.mark.django_db
class TestGabaritConnexion:
    def test_page_rend(self, client):
        reponse = client.get(reverse("accounts:login"))
        assert reponse.status_code == 200

    def test_revelation_mot_de_passe_est_native(self, client):
        html = client.get(reverse("accounts:login")).content.decode()
        assert 'data-password-toggle="id_password"' in html
        assert "data-password-icone-affiche" in html
        assert "data-password-icone-masque" in html
        # Le champ part masqué : la bascule est le fait de l'utilisateur.
        assert 'type="password"' in html

    def test_bouton_porte_un_libelle_accessible(self, client):
        html = client.get(reverse("accounts:login")).content.decode()
        assert 'aria-label="Afficher le mot de passe"' in html
        assert 'aria-pressed="false"' in html


@pytest.mark.django_db
class TestGabaritBase:
    def test_navigation_mobile_est_native(self, client):
        html = client.get(reverse("accounts:login")).content.decode()
        assert "data-nav-toggle" in html
        assert "data-nav-panel" in html
        assert 'aria-expanded="false"' in html

    def test_script_applicatif_est_charge(self, client):
        html = client.get(reverse("accounts:login")).content.decode()
        assert "js/iteag.js" in html

    def test_aucune_dependance_alpine(self, client):
        html = client.get(reverse("accounts:login")).content.decode()
        assert "alpine" not in html.lower(), "Alpine.js a été réintroduit — voir ADR-003."
        for directive in DIRECTIVES_INTERDITES:
            assert directive not in html, (
                f"La directive « {directive} » exige 'unsafe-eval' : "
                "elle est incompatible avec la CSP du projet (ADR-003)."
            )


@pytest.mark.django_db
class TestGabaritsPublics:
    """Les pages publiques principales rendent sans erreur."""

    @pytest.mark.parametrize(
        "nom_url",
        ["formations:parcours_list", "formations:professeur_list", "library:catalogue"],
    )
    def test_page_rend(self, client, nom_url):
        reponse = client.get(reverse(nom_url))
        assert reponse.status_code == 200

    @pytest.mark.parametrize(
        "nom_url",
        ["formations:parcours_list", "formations:professeur_list", "library:catalogue"],
    )
    def test_page_sans_directive_interdite(self, client, nom_url):
        html = client.get(reverse(nom_url)).content.decode()
        for directive in DIRECTIVES_INTERDITES:
            assert directive not in html


@pytest.mark.django_db
class TestBaliseVerset:
    def test_retourne_un_verset_complet(self):
        from apps.core.templatetags.iteag_tags import VERSETS, verset_aleatoire

        verset = verset_aleatoire()
        assert set(verset) == {"texte", "reference"}
        assert (verset["texte"], verset["reference"]) in VERSETS

    def test_rendu_serveur_dans_le_gabarit(self):
        from django.template import Context, Template

        rendu = Template("{% load iteag_tags %}{% verset_aleatoire as v %}{{ v.texte }}|{{ v.reference }}").render(
            Context({})
        )
        texte, reference = rendu.split("|")
        assert texte and reference
