"""Les teintes de petit texte doivent atteindre le niveau AA là où on les pose.

Le défaut mesuré : warm-500 (#978B72) ne donnait que 3.22:1 sur le fond crème
du site. Il n'est employé que pour du texte — mentions légales, légendes,
étiquettes de formulaire, en-têtes de tableau — dans 130 gabarits. Toutes ces
lignes échouaient au critère 1.4.3, sans qu'aucun contrôle ne le dise.

L'assombrissement corrige les fonds clairs et dégrade le fond sombre : la même
teinte ne peut pas servir des deux côtés. Le pied de page, entièrement en bleu
nuit, prend donc warm-400. Les deux sens sont vérifiés ici.
"""

import pathlib
import re

RACINE = pathlib.Path(__file__).resolve().parents[2]
CSS_SOURCE = RACINE / "assets" / "css" / "input.css"
PIED_DE_PAGE = RACINE / "templates" / "partials" / "footer.html"

AA_TEXTE_COURANT = 4.5


def teintes() -> dict[str, str]:
    css = CSS_SOURCE.read_text(encoding="utf-8")
    return dict(re.findall(r"--color-([a-z]+-\d+):\s*(#[0-9A-Fa-f]{6});", css))


def _canal(valeur: str) -> float:
    v = int(valeur, 16) / 255
    return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4


def luminance(couleur: str) -> float:
    c = couleur.lstrip("#")
    return 0.2126 * _canal(c[0:2]) + 0.7152 * _canal(c[2:4]) + 0.0722 * _canal(c[4:6])


def contraste(premier: str, second: str) -> float:
    a, b = luminance(premier), luminance(second)
    return (max(a, b) + 0.05) / (min(a, b) + 0.05)


def test_le_texte_discret_est_lisible_sur_les_fonds_clairs():
    palette = teintes()
    fonds = {"warm-50": palette["warm-50"], "blanc": "#FFFFFF"}
    for jeton in ("warm-500", "warm-600", "warm-700", "navy-700", "navy-800", "navy-900"):
        for nom_fond, fond in fonds.items():
            ratio = contraste(palette[jeton], fond)
            assert ratio >= AA_TEXTE_COURANT, f"{jeton} sur {nom_fond} : {ratio:.2f}:1"


def test_le_texte_discret_est_lisible_sur_le_bleu_nuit_du_pied_de_page():
    palette = teintes()
    ratio = contraste(palette["warm-400"], palette["navy-950"])
    assert ratio >= AA_TEXTE_COURANT, f"warm-400 sur navy-950 : {ratio:.2f}:1"


def test_le_pied_de_page_n_emploie_pas_la_teinte_reservee_aux_fonds_clairs():
    """warm-500, assombri pour le fond crème, ne contraste plus sur bleu nuit."""
    palette = teintes()
    assert contraste(palette["warm-500"], palette["navy-950"]) < AA_TEXTE_COURANT
    assert "text-warm-500" not in PIED_DE_PAGE.read_text(encoding="utf-8")
