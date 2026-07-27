"""
La barre publique doit rester courte, dire où l'on est, et ne rien cacher
derrière un survol.

Défauts corrigés ici, dans l'ordre où ils ont été trouvés :

1. **sept entrées à plat** dans la barre du site public, ce qui la rendait
   illisible et laissait toute nouvelle page s'y ajouter sans arbitrage ;
2. **« Formations vidéo » à côté de « Formations »**, comme s'il s'agissait
   d'une autre offre — alors que la vidéo est un format d'enseignement ;
3. **deux listes tenues à la main** — la barre et le menu mobile énuméraient
   les mêmes entrées dans le même gabarit, et avaient déjà divergé :
   « Bibliothèque » était une rubrique en haut de page et une sous-entrée
   « Ressources » sur mobile. Les rubriques sont désormais déclarées dans
   « apps/core/navigation.py » et rendues deux fois ;
4. **aucun état actif** — la règle « .nav-link.active » existait dans la
   feuille de style, aucun gabarit ne posait la classe. Sur « /formations/ »,
   rien ne disait qu'on était dans les formations ;
5. **les panneaux ne s'ouvraient qu'au survol** — au doigt, sur une tablette
   assez large pour recevoir la barre de bureau, le premier appui suivait le
   lien de l'intitulé et le panneau ne s'ouvrait jamais.

Le piège à éviter en corrigeant : un menu déroulant classique cache ses liens
derrière du JavaScript. Ici les panneaux s'ouvrent en CSS, et chaque intitulé
de rubrique reste un lien vers sa page principale — au clavier, à la souris,
sans script, aucune destination n'est hors d'atteinte. Le script n'ajoute
qu'un cas : l'ouverture au doigt.
"""

import pathlib
import re

import pytest
from django.urls import reverse

from apps.core.navigation import rubriques, rubriques_pour

RACINE = pathlib.Path(__file__).resolve().parents[2]
ENTETE = RACINE / "templates" / "partials" / "header.html"
STYLES = RACINE / "assets" / "css" / "input.css"
SCRIPT = RACINE / "static" / "js" / "iteag.js"

# Au-delà, la barre cesse d'être lisible d'un coup d'œil. Le nombre est un
# arbitrage, pas une loi : le relever demande de justifier l'ajout.
MAXIMUM_ENTREES = 4


class TestLaDeclaration:
    """Ce que les rubriques garantissent avant même d'être rendues."""

    def test_la_barre_reste_courte(self):
        entrees = len(rubriques())
        assert entrees <= MAXIMUM_ENTREES, f"{entrees} entrées dans la barre publique — au-delà de {MAXIMUM_ENTREES}"

    def test_chaque_rubrique_mene_quelque_part(self):
        """
        Un intitulé de rubrique qui n'est qu'un déclencheur laisse sans recours
        celui dont le panneau ne s'ouvre pas.
        """
        for rubrique in rubriques():
            assert rubrique.url not in ("", "#"), f"« {rubrique.libelle} » ne mène nulle part"

    def test_la_video_est_dans_la_rubrique_formations(self):
        """Elle ne doit plus voisiner « Formations » au premier niveau."""
        catalogue = reverse("elearning:catalogue")
        assert catalogue not in [r.url for r in rubriques()], "« E-Learning » est resté au premier niveau"
        sous_entrees = [entree.url for rubrique in rubriques() for entree in rubrique.entrees]
        assert catalogue in sous_entrees, "« E-Learning » n'est dans aucune rubrique"

    def test_aucune_rubrique_ne_revendique_la_racine(self):
        """« / » préfixe tout : une rubrique qui le revendique s'allume partout."""
        for rubrique in rubriques():
            assert "/" not in rubrique.chemins, f"« {rubrique.libelle} » revendique la racine"

    @pytest.mark.parametrize(
        "chemin,attendue",
        [
            ("/formations/", "formations"),
            ("/formations/professeurs/", "formations"),
            ("/e-learning/", "formations"),
            ("/presentation/", "institut"),
            ("/actualites/un-article/", "institut"),
            ("/bibliotheque/", "bibliotheque"),
            ("/", None),
            ("/connexion/", None),
        ],
    )
    def test_la_rubrique_active_suit_le_chemin(self, chemin, attendue):
        actives = [r.cle for r in rubriques_pour(chemin) if r.active]
        assert actives == ([attendue] if attendue else []), chemin

    def test_une_seule_rubrique_active_a_la_fois(self):
        """Deux intitulés soulignés diraient deux endroits en même temps."""
        for chemin in ("/formations/", "/formations/professeurs/", "/presentation/", "/bibliotheque/"):
            assert sum(1 for r in rubriques_pour(chemin) if r.active) <= 1, chemin


class TestCeQuiNeDependPasDuScript:
    """Le repli sans JavaScript est la base, pas une option."""

    def test_les_panneaux_ne_sont_pas_masques_par_l_attribut_hidden(self):
        """
        « display: none » ou l'attribut « hidden » rendrait les liens
        inatteignables sans script.
        """
        contenu = ENTETE.read_text(encoding="utf-8")
        assert "data-dropdown" not in contenu.split("{# Actions droite #}")[0], (
            "La barre publique ne doit pas dépendre du menu déroulant JavaScript"
        )
        for balise in re.findall(r"<[^>]*nav-groupe-panneau[^>]*>", contenu):
            assert not re.search(r"\shidden(?=[\s>])", balise), (
                f"Un panneau masqué par l'attribut « hidden » serait perdu sans script : {balise}"
            )

    def test_le_panneau_reste_dans_le_flux(self):
        styles = STYLES.read_text(encoding="utf-8")
        depart = styles.index(".nav-groupe-panneau {")
        regle = styles[depart : styles.index("\n  }", depart)]
        # Les commentaires parlent de « display: none » pour expliquer qu'on
        # l'évite : les retirer avant d'examiner les déclarations.
        declarations = re.sub(r"/\*.*?\*/", "", regle, flags=re.S)
        assert "display: none" not in declarations, (
            "Le panneau doit rester dans le flux, sinon il sort du parcours au clavier"
        )

    def test_le_panneau_s_ouvre_au_survol_et_au_focus(self):
        styles = STYLES.read_text(encoding="utf-8")
        for selecteur in (
            ".nav-groupe:hover .nav-groupe-panneau",
            ".nav-groupe:focus-within .nav-groupe-panneau",
        ):
            assert selecteur in styles, f"{selecteur} manque — le panneau dépendrait du script"

    def test_le_script_ouvre_aussi_au_doigt(self):
        """
        Sur une tablette large, « :hover » ne se déclenche pas : sans ce
        complément, les entrées des rubriques sont inatteignables.
        """
        assert ".nav-groupe.ouverte .nav-groupe-panneau" in STYLES.read_text(encoding="utf-8")
        script = SCRIPT.read_text(encoding="utf-8")
        assert "initRubriques" in script
        assert "(hover: none)" in script, "L'ouverture au clic doit rester réservée aux écrans sans survol"

    def test_les_icones_du_bouton_mobile_ne_passent_pas_par_la_propriete_hidden(self):
        """
        SVGElement n'expose pas « hidden » : l'affectation ne posait aucun
        attribut, la croix ne s'affichait jamais et le trait triple restait.
        """
        script = SCRIPT.read_text(encoding="utf-8")
        assert not re.search(r"icone\w*\.hidden\s*=", script), (
            "Une icône SVG ne se masque pas par la propriété « hidden » — utiliser l'attribut"
        )
        assert 'setAttribute("hidden"' in script


@pytest.mark.django_db
class TestCeQueLeVisiteurRecoit:
    """Vérifié sur le rendu : un gabarit juste mal inclus ne servirait à rien."""

    def _page(self, client, chemin=None) -> str:
        return client.get(chemin or reverse("elearning:catalogue")).content.decode()

    def test_les_rubriques_sont_rendues(self, client):
        contenu = self._page(client)
        assert "Formations" in contenu
        assert "L&#x27;institut" in contenu or "L'institut" in contenu

    @pytest.mark.parametrize(
        "nom_route",
        ["formations:parcours_list", "elearning:catalogue", "formations:professeur_list", "library:catalogue"],
    )
    def test_aucune_destination_n_a_disparu(self, client, nom_route):
        """Regrouper ne veut pas dire retirer : tout ce qui était atteignable le reste."""
        assert reverse(nom_route) in self._page(client), nom_route

    def test_les_pages_editoriales_restent_atteignables(self, client):
        contenu = self._page(client)
        for chemin in ("/presentation/", "/actualites/", "/contact/"):
            assert chemin in contenu, chemin

    def test_le_menu_mobile_deplie_toutes_les_rubriques(self, client):
        """
        Sur mobile, un panneau qui s'ouvre en cacherait un autre : les rubriques
        y sont dépliées sous leur intitulé.
        """
        contenu = self._page(client)
        groupes = [rubrique for rubrique in rubriques() if rubrique.entrees]
        assert contenu.count("nav-mobile-groupe") >= len(groupes)
        assert contenu.count("nav-mobile-lien") >= sum(len(r.entrees) for r in groupes)

    def test_toute_destination_declaree_est_servie(self, client):
        """Le défaut d'origine : deux listes saisies à la main, déjà divergentes."""
        contenu = self._page(client)
        for rubrique in rubriques():
            assert rubrique.url in contenu, rubrique.libelle
            for entree in rubrique.entrees:
                assert entree.url in contenu, f"{rubrique.libelle} → {entree.libelle}"

    def test_le_menu_mobile_ne_souligne_que_l_entree_courante(self, client):
        """Tout déplier puis tout souligner ne dirait plus rien."""
        contenu = self._page(client, reverse("formations:parcours_list"))
        assert contenu.count("nav-mobile-lien active") == 1

    def test_les_deux_rendus_parcourent_la_meme_declaration(self):
        """Ce qui rend la divergence impossible, et non seulement improbable."""
        gabarit = ENTETE.read_text(encoding="utf-8")
        barre, mobile = gabarit.split("{# ── Menu mobile ── #}")
        assert barre.count("for rubrique in navigation_publique") == 1
        assert mobile.count("for rubrique in navigation_publique") == 1

    def test_la_rubrique_courante_est_marquee(self, client):
        """Sur « /formations/ », la barre doit dire qu'on est dans les formations."""
        contenu = self._page(client, reverse("formations:parcours_list"))
        assert "nav-link active" in contenu, "Aucune rubrique active sur sa propre page"
        assert 'aria-current="true"' in contenu, "L'état actif n'est pas annoncé aux technologies d'assistance"

    def test_aucune_rubrique_marquee_hors_de_son_domaine(self, client):
        contenu = self._page(client, reverse("accounts:login"))
        assert "nav-link active" not in contenu
