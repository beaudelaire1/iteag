#!/usr/bin/env python3
"""Migration des styles inline des pages web Django vers une feuille CSS.

Le contrôle CSP concerne les réponses HTML exécutées par un navigateur. Les
emails HTML et les documents PDF sont des artefacts de rendu distincts : ils ne
reçoivent pas l'en-tête CSP du site et certains moteurs de messagerie/PDF ont
besoin de CSS embarqué. Ils sont donc explicitement hors périmètre ici, au lieu
d'être modifiés par un codemod qui casserait leur rendu.

Pour les pages web, seuls les ``style="..."`` entièrement statiques sont
convertis en classes déterministes. Toute valeur Django dynamique reste visible
comme anomalie et doit être remplacée par un composant typé.

Usage depuis ``src/``::

    python scripts/migrer_styles_inline.py --write
    python scripts/migrer_styles_inline.py --check
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
TEMPLATES = RACINE / "templates"
CSS_GENERE = RACINE / "assets" / "css" / "inline-migre.css"

BALISE = re.compile(r"<([A-Za-z][^<>]*?)>", re.DOTALL)
STYLE_ATTR = re.compile(r"\sstyle=(?P<quote>[\"'])(?P<css>.*?)(?P=quote)", re.DOTALL | re.IGNORECASE)
CLASS_ATTR = re.compile(r"\sclass=(?P<quote>[\"'])(?P<classes>.*?)(?P=quote)", re.DOTALL | re.IGNORECASE)
STYLE_BLOCK = re.compile(r"<style(?:\s[^>]*)?>.*?</style\s*>", re.DOTALL | re.IGNORECASE)
DJANGO = ("{{", "{%", "{#")


def est_artefact_non_web(path: Path) -> bool:
    """Emails/PDF ne sont pas des documents soumis à la CSP du navigateur."""
    relatif = path.relative_to(TEMPLATES)
    parties = {partie.lower() for partie in relatif.parts[:-1]}
    nom = relatif.name.lower()
    return (
        "emails" in parties
        or "pdf" in parties
        or nom.endswith("_email.html")
        or nom.endswith("_pdf.html")
    )


def normaliser_css(css: str) -> str:
    return css.strip()


def nom_classe(css: str) -> str:
    empreinte = hashlib.sha256(css.encode("utf-8")).hexdigest()[:12]
    return f"csp-style-{empreinte}"


def migrer_balise(texte: str, regles: dict[str, str]) -> tuple[str, int, list[str]]:
    styles = list(STYLE_ATTR.finditer(texte))
    if not styles:
        return texte, 0, []
    if len(styles) > 1:
        raise ValueError(f"Plusieurs attributs style dans une même balise : {texte[:160]!r}")

    style = styles[0]
    css = normaliser_css(style.group("css"))
    if any(marqueur in css for marqueur in DJANGO):
        return texte, 0, [css]

    classe = nom_classe(css)
    regles[classe] = css

    sans_style = texte[: style.start()] + texte[style.end() :]
    classe_existante = CLASS_ATTR.search(sans_style)
    if classe_existante:
        classes = classe_existante.group("classes").rstrip()
        nouvelles = f"{classes} {classe}" if classes else classe
        sans_style = (
            sans_style[: classe_existante.start("classes")]
            + nouvelles
            + sans_style[classe_existante.end("classes") :]
        )
    else:
        fin_nom = re.match(r"<([A-Za-z][A-Za-z0-9:-]*)", sans_style)
        if not fin_nom:
            raise ValueError(f"Balise HTML inattendue : {texte[:160]!r}")
        position = fin_nom.end()
        sans_style = f'{sans_style[:position]} class="{classe}"{sans_style[position:]}'

    return sans_style, 1, []


def migrer_fichier(path: Path, *, ecrire: bool, regles: dict[str, str]) -> tuple[int, list[str], int]:
    original = path.read_text(encoding="utf-8")
    dynamiques: list[str] = []
    migres = 0

    def remplacer(match: re.Match[str]) -> str:
        nonlocal migres
        balise = match.group(0)
        nouvelle, nombre, restants = migrer_balise(balise, regles)
        migres += nombre
        dynamiques.extend(restants)
        return nouvelle

    transforme = BALISE.sub(remplacer, original)
    blocs_style = len(STYLE_BLOCK.findall(transforme))
    if ecrire and transforme != original:
        path.write_text(transforme, encoding="utf-8")
    return migres, dynamiques, blocs_style


def ecrire_css(regles: dict[str, str]) -> None:
    lignes = [
        "/* Fichier généré par scripts/migrer_styles_inline.py.",
        "   Ne pas éditer à la main : les classes correspondent aux anciennes",
        "   déclarations inline migrées afin de permettre une CSP sans unsafe-inline. */",
        "",
    ]
    for classe, css in sorted(regles.items()):
        lignes.append(f".{classe} {{ {css} }}")
    lignes.append("")
    CSS_GENERE.write_text("\n".join(lignes), encoding="utf-8")


def pages_web() -> list[Path]:
    return [path for path in sorted(TEMPLATES.rglob("*.html")) if not est_artefact_non_web(path)]


def scanner(*, ecrire: bool) -> tuple[int, list[tuple[Path, str]], list[Path]]:
    regles: dict[str, str] = {}
    total = 0
    dynamiques: list[tuple[Path, str]] = []
    blocs: list[Path] = []

    for path in pages_web():
        migres, restants, nb_blocs = migrer_fichier(path, ecrire=ecrire, regles=regles)
        total += migres
        dynamiques.extend((path, css) for css in restants)
        if nb_blocs:
            blocs.append(path)

    if ecrire:
        ecrire_css(regles)
    return total, dynamiques, blocs


def verifier_aucun_inline() -> tuple[list[tuple[Path, str]], list[Path]]:
    attributs: list[tuple[Path, str]] = []
    blocs: list[Path] = []
    for path in pages_web():
        contenu = path.read_text(encoding="utf-8")
        attributs.extend((path, match.group("css").strip()) for match in STYLE_ATTR.finditer(contenu))
        if STYLE_BLOCK.search(contenu):
            blocs.append(path)
    return attributs, blocs


def relatif(path: Path) -> str:
    return str(path.relative_to(RACINE))


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args()

    if args.write:
        total, dynamiques, blocs = scanner(ecrire=True)
        print(f"Styles statiques web migrés : {total}")
        print(
            "Classes CSS générées : "
            + str(
                sum(
                    1
                    for ligne in CSS_GENERE.read_text(encoding="utf-8").splitlines()
                    if ligne.startswith(".csp-style-")
                )
            )
        )
        if dynamiques:
            print("Styles dynamiques web laissés pour correction manuelle :")
            for path, css in dynamiques:
                print(f"- {relatif(path)}: {css}")
        if blocs:
            print("Blocs <style> web laissés pour externalisation manuelle :")
            for path in blocs:
                print(f"- {relatif(path)}")
        return 0

    attributs, blocs = verifier_aucun_inline()
    if not attributs and not blocs:
        print("OK — aucun style inline dans les pages web soumises à la CSP.")
        return 0

    if attributs:
        print("Attributs style interdits dans les pages web :")
        for path, css in attributs:
            print(f"- {relatif(path)}: {css}")
    if blocs:
        print("Blocs <style> interdits dans les pages web :")
        for path in blocs:
            print(f"- {relatif(path)}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
