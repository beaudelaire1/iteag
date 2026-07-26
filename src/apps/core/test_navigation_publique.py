"""
La barre publique doit rester courte, et rien n'y doit dépendre d'un survol.

Deux défauts corrigés ici :

1. **sept entrées à plat** dans la barre du site public, ce qui la rendait
   illisible et laissait toute nouvelle page s'y ajouter sans arbitrage ;
2. **« Formations vidéo » à côté de « Formations »**, comme s'il s'agissait
   d'une autre offre — alors que la vidéo est un format d'enseignement. La
   même confusion avait déjà été corrigée dans les espaces privés.

Le troisième point n'était pas un défaut mais un piège à éviter en corrigeant :
un menu déroulant classique cache ses liens derrière du JavaScript ou un
survol. Ici les panneaux s'ouvrent en CSS, et chaque intitulé de rubrique reste
un lien vers sa page principale — au clavier, à la souris, sans script, aucune
destination n'est hors d'atteinte.
"""

import pathlib
import re

import pytest
from django.urls import reverse

RACINE = pathlib.Path(__file__).resolve().parents[2]
ENTETE = RACINE / "templates" / "partials" / "header.html"

# Au-delà, la barre cesse d'être lisible d'un coup d'œil. Le nombre est un
# arbitrage, pas une loi : le relever demande de justifier l'ajout.
MAXIMUM_ENTREES = 4


def barre_bureau(html: str) -> str:
    """Portion du gabarit qui rend la barre visible sur grand écran."""
    depart = html.index('<div class="hidden lg:flex lg:items-center lg:gap-8">')
    return html[depart : html.index("{# Actions droite #}", depart)]


def test_la_barre_reste_courte():
    contenu = barre_bureau(ENTETE.read_text())
    # Une entrée = un lien de premier niveau, rubrique ou page.
    entrees = len(re.findall(r'class="nav-link"', contenu))
    assert entrees <= MAXIMUM_ENTREES, f"{entrees} entrées dans la barre publique — au-delà de {MAXIMUM_ENTREES}"


def test_la_video_est_dans_la_rubrique_formations():
    """Elle ne doit plus voisiner « Formations » au premier niveau."""
    contenu = barre_bureau(ENTETE.read_text())
    for panneau in re.findall(r'<div class="nav-groupe-panneau">(.*?)</div>', contenu, re.S):
        if "elearning:catalogue" in panneau:
            return
    pytest.fail("« Formations vidéo » n'est dans aucune rubrique — elle est restée au premier niveau")


def test_chaque_rubrique_mene_quelque_part():
    """
    Un intitulé de rubrique qui n'est qu'un déclencheur laisse sans recours
    celui dont le panneau ne s'ouvre pas.
    """
    contenu = barre_bureau(ENTETE.read_text())
    groupes = re.findall(r'<div class="nav-groupe">(.*?)</div>\s*</div>', contenu, re.S)
    assert groupes, "Aucune rubrique trouvée dans la barre"
    for groupe in groupes:
        intitule = re.search(r'<a href="([^"]+)"[^>]*class="nav-link"', groupe)
        assert intitule, "Un intitulé de rubrique n'est pas un lien"
        assert intitule.group(1) not in ("", "#"), "Un intitulé de rubrique ne mène nulle part"


def test_les_panneaux_ne_dependent_pas_du_javascript():
    """
    « display: none » ou l'attribut « hidden » rendrait les liens inatteignables
    sans script. L'ouverture se fait en CSS, au survol et à la prise de focus.
    """
    contenu = barre_bureau(ENTETE.read_text())
    assert "data-dropdown" not in contenu, "La barre publique ne doit pas dépendre du menu déroulant JavaScript"
    # L'attribut « hidden » sur une balise, à ne pas confondre avec la classe
    # utilitaire « hidden lg:flex » qui masque la barre entière sur mobile.
    for balise in re.findall(r"<[^>]*nav-groupe-panneau[^>]*>", contenu):
        assert not re.search(r"\shidden(?=[\s>])", balise), (
            f"Un panneau masqué par l'attribut « hidden » serait perdu sans script : {balise}"
        )

    styles = (RACINE / "assets" / "css" / "input.css").read_text()
    depart = styles.index(".nav-groupe-panneau {")
    regle = styles[depart : styles.index("\n  }", depart)]
    # Les commentaires parlent de « display: none » pour expliquer qu'on
    # l'évite : les retirer avant d'examiner les déclarations.
    declarations = re.sub(r"/\*.*?\*/", "", regle, flags=re.S)
    assert "display: none" not in declarations, (
        "Le panneau doit rester dans le flux, sinon il sort du parcours au clavier"
    )
    assert ".nav-groupe:focus-within .nav-groupe-panneau" in styles, "Le panneau doit s'ouvrir à la prise de focus"


@pytest.mark.django_db
class TestCeQueLeVisiteurRecoit:
    """Vérifié sur le rendu : un gabarit juste mal inclus ne servirait à rien."""

    def _accueil(self, client) -> str:
        return client.get(reverse("elearning:catalogue")).content.decode()

    def test_les_rubriques_sont_rendues(self, client):
        contenu = self._accueil(client)
        assert "Formations" in contenu
        assert "L&#x27;institut" in contenu or "L'institut" in contenu

    @pytest.mark.parametrize(
        "nom_route",
        ["formations:parcours_list", "elearning:catalogue", "formations:professeur_list", "library:catalogue"],
    )
    def test_aucune_destination_n_a_disparu(self, client, nom_route):
        """Regrouper ne veut pas dire retirer : tout ce qui était atteignable le reste."""
        assert reverse(nom_route) in self._accueil(client), nom_route

    def test_les_pages_editoriales_restent_atteignables(self, client):
        contenu = self._accueil(client)
        for chemin in ("/presentation/", "/actualites/", "/contact/"):
            assert chemin in contenu, chemin

    def test_le_menu_mobile_deplie_les_rubriques(self, client):
        """
        Sur mobile, un panneau qui s'ouvre en cacherait un autre : les rubriques
        y sont dépliées sous leur intitulé.
        """
        contenu = self._accueil(client)
        assert contenu.count("nav-mobile-groupe") >= 3
