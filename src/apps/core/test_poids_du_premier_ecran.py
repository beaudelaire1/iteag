"""Ce que coûte le premier écran, mesuré sur les fichiers qu'on livre.

Deux défauts mesurés sur la préproduction, que ces contrôles empêchent de
revenir :

1. le titre d'accueil — l'élément que Lighthouse mesure comme « plus grand
   rendu » — partait d'une opacité nulle et n'était révélé que par un
   observateur d'intersection lancé par un script différé : 2,1 s de retard
   pour un texte pourtant présent dans le HTML servi ;
2. Inter et Playfair étaient livrées entières, cyrillique et vietnamien
   compris : 490 Kio de polices sur la page d'accueil, en concurrence de bande
   passante avec ce même titre.
"""

import pathlib
import re

RACINE = pathlib.Path(__file__).resolve().parents[2]
CSS_SOURCE = RACINE / "assets" / "css" / "input.css"
JS_GLOBAL = RACINE / "static" / "js" / "iteag.js"
POLICES = RACINE / "static" / "fonts"
BASE = RACINE / "templates" / "base.html"

# Une police du premier écran dépasse rarement 25 Kio une fois réduite au latin
# courant. Le plafond laisse de la marge sans laisser passer une police entière.
PLAFOND_OCTETS = 40 * 1024


def test_l_entree_du_heros_est_decrite_par_la_feuille_de_style():
    css = CSS_SOURCE.read_text(encoding="utf-8")
    depart = css.index("[data-motion-hero] .reveal {")
    bloc = css[depart : css.index("}", depart)]
    assert "animation:" in bloc, "L'entrée du héros doit partir du premier rendu, pas d'une classe posée par un script."


def test_le_script_global_ne_touche_plus_au_heros():
    js = JS_GLOBAL.read_text(encoding="utf-8")
    lignes = [ligne for ligne in js.splitlines() if "data-motion-hero" in ligne and not ligne.strip().startswith("//")]
    assert not lignes, f"Le héros redevient tributaire du script : {lignes}"


def test_le_premier_ecran_precharge_ses_deux_polices():
    base = BASE.read_text(encoding="utf-8")
    preloads = re.findall(r'<link rel="preload"[^>]*href="\{% static \'fonts/([^\']+)\'', base)
    assert set(preloads) == {"PlayfairDisplay-700.woff2", "Inter-400.woff2"}, preloads
    for nom in preloads:
        assert (POLICES / nom).exists(), nom


def test_aucune_police_livree_ne_depasse_le_plafond():
    fichiers = sorted(POLICES.glob("*.woff2"))
    assert fichiers, "Aucune police auto-hébergée trouvée"
    trop_lourdes = {
        fichier.name: fichier.stat().st_size for fichier in fichiers if fichier.stat().st_size > PLAFOND_OCTETS
    }
    assert not trop_lourdes, f"Polices non réduites (relancer scripts/reduire_polices.py) : {trop_lourdes}"


def test_chaque_police_declare_la_plage_qu_elle_couvre():
    """Sans « unicode-range », le navigateur télécharge tous les sous-ensembles."""
    fonts_css = (POLICES / "fonts.css").read_text(encoding="utf-8")
    declarations = fonts_css.count("@font-face")
    assert declarations >= 7, declarations
    assert fonts_css.count("unicode-range:") == declarations
    assert fonts_css.count("font-display: swap") == declarations

    # Chaque fichier déclaré doit exister, et chaque fichier présent être déclaré.
    declares = set(re.findall(r"url\('([^']+)'\)", fonts_css))
    presents = {fichier.name for fichier in POLICES.glob("*.woff2")}
    assert declares == presents, declares ^ presents
