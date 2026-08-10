#!/usr/bin/env python3
"""Remplace les derniers styles Django dynamiques par des données typées.

Ce script ne contient aucun remplacement générique de CSS. Chaque motif est
fermé et documenté : largeur en pourcentage, délai d'animation, couleur de
badge/groupe, ou état visuel. Toute déclaration qui ne correspond pas à l'un de
ces contrats reste dans le gabarit et fait échouer le contrôle CSP suivant.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
TEMPLATES = RACINE / "templates"


def est_artefact_non_web(path: Path) -> bool:
    relatif = path.relative_to(TEMPLATES)
    parties = {partie.lower() for partie in relatif.parts[:-1]}
    nom = relatif.name.lower()
    return "emails" in parties or "pdf" in parties or nom.endswith("_email.html") or nom.endswith("_pdf.html")


REMPLACEMENTS_DIRECTS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r'''\sstyle="width:\s*\{\{\s*([^{}]+?)\s*\}\}%\s*;?"'''),
        r''' data-progress-width="{{ \1 }}"''',
    ),
    (
        re.compile(r'''\sstyle="width:\s*\{%\s*widthratio\s+(.+?)\s*%\}%\s*;?"'''),
        r''' data-progress-width="{% widthratio \1 %}"''',
    ),
    (
        re.compile(r'''\sstyle="transition-delay:\s*\{\{\s*forloop\.counter0\s*\}\}([0-9]+)ms\s*;?"'''),
        r''' data-transition-delay="{{ forloop.counter0 }}\1"''',
    ),
    (
        re.compile(r'''\sstyle="background:\s*\{\{\s*groupe\.couleur\s*\}\}\s*;?"'''),
        r''' data-background-color="{{ groupe.couleur }}"''',
    ),
    (
        re.compile(r'''\sstyle="--iteag-editor-min-height:\s*\{\{\s*min_height\|default:'18rem'\s*\}\}\s*;?"'''),
        "",
    ),
    (
        re.compile(
            r'''\sstyle="width:\s*\{\{\s*item\.pourcentage\s*\}\}%\s*;\s*background:\s*var\(--color-navy-700\)\s*;?"'''
        ),
        r''' data-progress-width="{{ item.pourcentage }}"''',
    ),
    (
        re.compile(
            r'''\sstyle="\{%\s*if\s+([^%]+?)\s*%\}background:\s*var\(--color-navy-800\);\s*color:\s*#fff;\{%\s*else\s*%\}color:\s*var\(--color-navy-600\);\{%\s*endif\s*%\}"'''
        ),
        r''' data-pagination-state="{% if \1 %}current{% else %}available{% endif %}"''',
    ),
    (
        re.compile(
            r'''\sstyle="color:\s*\{%\s*if\s+choix\.correct\s*%\}var\(--color-navy-900\)\{%\s*else\s*%\}var\(--color-warm-600\)\{%\s*endif\s*%\};?"'''
        ),
        r''' data-question-choice-state="{% if choix.correct %}correct{% else %}neutral{% endif %}"''',
    ),
    (
        re.compile(
            r'''\sstyle="\{%\s*if\s+not\s+forloop\.last\s*%\}border-bottom:\s*1px\s+solid\s+var\(--color-warm-150\);\s*padding-bottom:\s*8px;\{%\s*endif\s*%\}"'''
        ),
        r''' data-divider-state="{% if not forloop.last %}active{% endif %}"''',
    ),
    # L'état d'une échéance est binaire ; le gabarit transmet cet état, pas les
    # deux couleurs CSS entre lesquelles il choisit.
    (
        re.compile(
            r'''\sstyle="color:\s*\{%\s*if\s+echeance\.jours_restants\s*<=\s*7\s*%\}var\(--color-gold-600\)\{%\s*else\s*%\}var\(--color-warm-400\)\{%\s*endif\s*%\};?"'''
        ),
        r''' data-deadline-state="{% if echeance.jours_restants <= 7 %}urgent{% else %}normal{% endif %}"''',
    ),
)

STYLE_ATTR = re.compile(r'''\sstyle=(?P<q>["'])(?P<css>.*?)(?P=q)''', re.DOTALL | re.IGNORECASE)


def migrer(contenu: str) -> tuple[str, int]:
    total = 0
    resultat = contenu
    for motif, remplacement in REMPLACEMENTS_DIRECTS:
        resultat, nombre = motif.subn(remplacement, resultat)
        total += nombre
    return resultat, total


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args()

    total = 0
    restants: list[tuple[Path, str]] = []
    for path in sorted(TEMPLATES.rglob("*.html")):
        if est_artefact_non_web(path):
            continue
        original = path.read_text(encoding="utf-8")
        transforme, nombre = migrer(original)
        total += nombre
        if args.write and transforme != original:
            path.write_text(transforme, encoding="utf-8")
        contenu_a_verifier = transforme if args.write else original
        restants.extend((path, m.group("css").strip()) for m in STYLE_ATTR.finditer(contenu_a_verifier))

    if args.write:
        print(f"Styles dynamiques typés migrés : {total}")
    if restants:
        print("Styles web encore non couverts :")
        for path, css in restants:
            print(f"- {path.relative_to(RACINE)}: {css}")
        return 1 if args.check else 0

    print("OK — aucun attribut style ne subsiste dans les pages web.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
