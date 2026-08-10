#!/usr/bin/env python3
"""Remplace les classes CSP temporaires par des utilitaires lisibles.

La première migration a déplacé mécaniquement les styles inline vers des
classes ``csp-style-<empreinte>``. C'était sûr pour la CSP, mais mauvais pour la
maintenance : l'intention n'est plus visible dans le gabarit.

Ce second passage transforme chaque déclaration CSS en utilitaire Tailwind
explicite (standard quand il existe, valeur arbitraire sinon). Les deux motifs
SVG historiques deviennent des classes nommées du design system. Après
exécution, aucune classe hashée ne doit subsister.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
TEMPLATES = RACINE / "templates"
CSS_TEMPORAIRE = RACINE / "assets" / "css" / "inline-migre.css"

REGLE = re.compile(r"^\.(csp-style-[0-9a-f]{12})\s*\{\s*(.*?)\s*\}\s*$")
VAR_COULEUR = re.compile(r"^var\(--color-([a-z0-9-]+)(?:,\s*[^)]+)?\)$", re.I)

COULEURS_HEX = {
    "#059669": "emerald-600",
    "#065f46": "emerald-800",
    "#ecfdf5": "emerald-50",
    "#fef2f2": "red-50",
    "#b91c1c": "red-700",
    "#991b1b": "red-800",
}

MOTIFS = {
    "60": "bg-pattern-crosses-soft",
    "80": "bg-pattern-dots-light",
}


def compact(valeur: str) -> str:
    """Encode les espaces d'une valeur arbitraire selon la syntaxe Tailwind."""
    return re.sub(r"\s+", "_", valeur.strip())


def couleur_token(prefixe: str, valeur: str) -> str | None:
    valeur = valeur.strip()
    match = VAR_COULEUR.match(valeur)
    if match:
        return f"{prefixe}-{match.group(1)}"
    if valeur.lower() == "white":
        return f"{prefixe}-white"
    nom = COULEURS_HEX.get(valeur.lower())
    if nom:
        return f"{prefixe}-{nom}"
    return None


def utilitaire(propriete: str, valeur: str) -> str:
    propriete = propriete.strip().lower()
    valeur = valeur.strip()

    if propriete == "color":
        return couleur_token("text", valeur) or f"[color:{compact(valeur)}]"
    if propriete == "background":
        token = couleur_token("bg", valeur)
        if token:
            return token
        return f"[background:{compact(valeur)}]"
    if propriete == "border-color":
        return couleur_token("border", valeur) or f"[border-color:{compact(valeur)}]"
    if propriete == "fill":
        return couleur_token("fill", valeur) or f"[fill:{compact(valeur)}]"

    simples = {
        ("margin", "0"): "m-0",
        ("margin-bottom", "0"): "mb-0",
        ("margin-top", "1rem"): "mt-4",
        ("padding", "0"): "p-0",
        ("padding-right", "2.5rem"): "pr-10",
        ("padding-left", "2.75rem"): "pl-11",
        ("padding-top", "2.5rem"): "pt-10",
        ("padding-top", "3.5rem"): "pt-14",
        ("white-space", "pre-line"): "whitespace-pre-line",
        ("overflow-x", "auto"): "overflow-x-auto",
        ("text-align", "right"): "text-right",
        ("max-width", "none"): "max-w-none",
        ("width", "100%"): "w-full",
        ("height", "2px"): "h-0.5",
        ("scroll-margin-top", "5rem"): "scroll-mt-20",
        ("position", "absolute"): "absolute",
        ("left", "-9999px"): "-left-[9999px]",
        ("border", "none"): "border-0",
        ("display", "none !important"): "hidden",
        ("display", "none!important"): "hidden",
    }
    cle = (propriete, valeur.lower())
    if cle in simples:
        return simples[cle]

    prefixes = {
        "font-size": "text",
        "line-height": "leading",
        "letter-spacing": "tracking",
        "width": "w",
        "height": "h",
        "min-width": "min-w",
        "max-width": "max-w",
        "min-height": "min-h",
        "max-height": "max-h",
        "top": "top",
        "transition-delay": "delay",
        "box-shadow": "shadow",
    }
    prefixe = prefixes.get(propriete)
    if prefixe:
        return f"{prefixe}-[{compact(valeur)}]"

    return f"[{propriete}:{compact(valeur)}]"


def parse_declarations(css: str) -> list[tuple[str, str]]:
    declarations = []
    for morceau in css.split(";"):
        morceau = morceau.strip()
        if not morceau:
            continue
        if ":" not in morceau:
            raise ValueError(f"Déclaration CSS invalide : {morceau!r}")
        propriete, valeur = morceau.split(":", 1)
        declarations.append((propriete.strip(), valeur.strip()))
    return declarations


def utilitaires_pour_regle(css: str) -> str:
    """Traite les data-URI avant le parseur générique de déclarations."""
    if css.startswith("background-image:") and "data:image/svg+xml" in css:
        if "width=&quot;60&quot;" in css:
            return MOTIFS["60"]
        if "width=&quot;80&quot;" in css:
            return MOTIFS["80"]
        raise ValueError("Motif SVG historique non reconnu : nommer le composant explicitement.")

    utilitaires = [utilitaire(prop, valeur) for prop, valeur in parse_declarations(css)]
    return " ".join(dict.fromkeys(utilitaires))


def construire_mapping() -> dict[str, str]:
    mapping: dict[str, str] = {}
    for ligne in CSS_TEMPORAIRE.read_text(encoding="utf-8").splitlines():
        match = REGLE.match(ligne.strip())
        if not match:
            continue
        classe, css = match.groups()
        mapping[classe] = utilitaires_pour_regle(css)
    if len(mapping) < 190:
        raise SystemExit(f"Feuille temporaire incomplète : seulement {len(mapping)} règles trouvées.")
    return mapping


def remplacer(mapping: dict[str, str], *, ecrire: bool) -> int:
    total = 0
    for path in sorted(TEMPLATES.rglob("*.html")):
        contenu = path.read_text(encoding="utf-8")
        transforme = contenu
        for classe, utilitaires in mapping.items():
            if classe in transforme:
                occurrences = transforme.count(classe)
                transforme = transforme.replace(classe, utilitaires)
                total += occurrences
        if ecrire and transforme != contenu:
            path.write_text(transforme, encoding="utf-8")
    return total


def verifier() -> list[Path]:
    return [
        path
        for path in sorted(TEMPLATES.rglob("*.html"))
        if "csp-style-" in path.read_text(encoding="utf-8")
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args()

    if args.write:
        mapping = construire_mapping()
        nombre = remplacer(mapping, ecrire=True)
        CSS_TEMPORAIRE.write_text(
            "/* Migration terminée : les gabarits utilisent désormais des utilitaires lisibles. */\n",
            encoding="utf-8",
        )
        print(f"Classes CSP temporaires remplacées : {nombre} occurrences, {len(mapping)} règles.")

    restants = verifier()
    if restants:
        print("Classes CSP opaques encore présentes :")
        for path in restants:
            print(f"- {path.relative_to(RACINE)}")
        return 1
    print("OK — aucune classe csp-style-* ne subsiste dans les gabarits.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
