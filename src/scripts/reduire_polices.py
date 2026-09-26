"""Réduit les polices auto-hébergées aux caractères réellement écrits.

Inter est livrée avec 2 849 glyphes : cyrillique, vietnamien, alphabet
phonétique. Un visiteur téléchargeait donc 445 Kio d'alphabets qu'aucune page
n'affiche, en concurrence de bande passante avec le titre qu'il attend. Le
découpage garde le latin courant pour tout le site, et isole dans des fichiers
séparés le latin étendu et le grec — utile aux citations du Nouveau Testament.
« unicode-range » fait le reste : le navigateur ne demande ces fichiers que
s'il rencontre un caractère qui les concerne.

Le script régénère aussi fonts.css, pour que les plages déclarées au navigateur
soient exactement celles qui ont servi au découpage. Il part toujours des .ttf
d'origine, jamais des .woff2 déjà réduits : on peut le relancer sans risque.
"""

from __future__ import annotations

from pathlib import Path

from fontTools.subset import Options, Subsetter, parse_unicodes
from fontTools.ttLib import TTFont

POLICES = Path(__file__).resolve().parents[1] / "static" / "fonts"

# Latin courant : français, créole, ponctuation typographique, symboles
# monétaires et diacritiques combinants (le « é » écrit en deux codets).
LATIN = (
    "U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,"
    "U+0300-0304,U+0308,U+0327,U+0329,U+2000-206F,U+2074,U+20AC,U+2122,"
    "U+2190-2193,U+2212,U+2215,U+FEFF,U+FFFD"
)
# Latin étendu : polonais, tchèque, turc, roumain, vietnamien. Rare sur le
# site, donc isolé : le navigateur ne le demande que s'il en croise un signe.
LATIN_ETENDU = "U+0100-02AF,U+0305-036F,U+1E00-1EFF,U+2020,U+20A0-20AB,U+20AD-20CF,U+2113,U+2C60-2C7F,U+A720-A7FF"
# Grec moderne et polytonique (grec ancien du texte biblique).
GREC = "U+0370-03FF,U+1F00-1FFF"

PLAGES = (("latin", LATIN), ("etendu", LATIN_ETENDU), ("grec", GREC))

# L'ordre compte. « œ » ou « ĳ » appartiennent au bloc U+0100-02AF du latin
# étendu tout en étant du français courant : ils figurent dans les deux
# découpes. Quand deux fontes d'une même famille couvrent un caractère, le
# navigateur retient la dernière déclarée. Le latin courant est donc écrit en
# dernier, sinon « œuvrant » suffisait à faire télécharger 31 Kio de latin
# étendu sur la page d'accueil.
ORDRE_DECLARATION = ("etendu", "grec", "latin")

# (source .ttf, famille CSS, style, graisse, plages découpées)
POLICES_DECLAREES = (
    ("Inter-400", "Inter", "normal", 400, ("latin", "etendu", "grec")),
    ("Inter-500", "Inter", "normal", 500, ("latin", "etendu")),
    ("Inter-600", "Inter", "normal", 600, ("latin", "etendu")),
    ("Inter-700", "Inter", "normal", 700, ("latin", "etendu", "grec")),
    ("PlayfairDisplay-400", "Playfair Display", "normal", 400, ("latin", "etendu")),
    ("PlayfairDisplay-700", "Playfair Display", "normal", 700, ("latin", "etendu")),
    ("PlayfairDisplay-Italic-400", "Playfair Display", "italic", 400, ("latin", "etendu")),
)

ENTETE = """/* ═══════════════════════════════════════
   Polices auto-hébergées — Standard TUS
   Zéro dépendance Google Fonts (RGPD)

   Fichier engendré par src/scripts/reduire_polices.py :
   toute modification manuelle sera écrasée au prochain découpage.
   ═══════════════════════════════════════ */
"""


def nom_fichier(base: str, plage: str) -> str:
    return base if plage == "latin" else f"{base}-{plage}"


def reduire(source: Path, plages: str, destination: Path) -> None:
    police = TTFont(source)
    options = Options()
    options.flavor = "woff2"
    options.layout_features = ["*"]
    options.name_IDs = ["*"]
    options.notdef_outline = True
    options.recalc_bounds = True
    subsetter = Subsetter(options=options)
    subsetter.populate(unicodes=parse_unicodes(plages))
    subsetter.subset(police)
    police.flavor = "woff2"
    police.save(destination)
    police.close()


def main() -> int:
    plages = dict(PLAGES)
    regles = [ENTETE]
    total = 0

    for base, famille, style, graisse, decoupes in POLICES_DECLAREES:
        source = POLICES / f"{base}.ttf"
        if not source.exists():
            raise SystemExit(f"Police source absente : {source}")
        for plage in (p for p in ORDRE_DECLARATION if p in decoupes):
            fichier = f"{nom_fichier(base, plage)}.woff2"
            destination = POLICES / fichier
            reduire(source, plages[plage], destination)
            poids = destination.stat().st_size
            total += poids
            print(f"{fichier:36} {poids / 1024:6.1f} Kio")
            regles.append(
                "\n@font-face {\n"
                f"  font-family: '{famille}';\n"
                f"  font-style: {style};\n"
                f"  font-weight: {graisse};\n"
                "  font-display: swap;\n"
                f"  src: url('{fichier}') format('woff2');\n"
                f"  unicode-range: {plages[plage].replace(',', ', ')};\n"
                "}\n"
            )

    (POLICES / "fonts.css").write_text("".join(regles), encoding="utf-8")
    print(f"\nTotal woff2 : {total / 1024:.1f} Kio — fonts.css régénéré.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
