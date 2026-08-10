#!/usr/bin/env python3
"""Vérifie les invariants CSP des pages HTML exécutées par un navigateur.

Les emails HTML et les gabarits PDF sont volontairement exclus : ils ne sont
pas servis comme pages web avec l'en-tête CSP et leurs moteurs de rendu exigent
souvent du CSS embarqué.

Ce contrôle est un garde-fou de maintenance, pas un outil de migration :
- aucun attribut ``style=`` ni bloc ``<style>`` dans les pages web ;
- aucun ``attrs={"style": ...}`` généré depuis le Python applicatif ;
- aucune ancienne classe de migration ``csp-style-*`` ;
- aucun gestionnaire JavaScript inline ``on...=`` ;
- CSP globale sans ``style-src 'unsafe-inline'`` ;
- HTMX configuré sans évaluation d'expressions ni scripts de fragments.

Les mutations ciblées de propriétés CSS via le CSSOM par un script déjà autorisé
ne sont pas assimilées ici à du CSS inline source : CSP 3 distingue les
attributs de style des opérations CSSOM, et réserve notamment ``unsafe-eval``
aux opérations qui parsèrent des règles ou des blocs de déclarations complets.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
TEMPLATES = RACINE / "templates"
APPS = RACINE / "apps"
BASE = RACINE / "config" / "settings" / "base.py"
BASE_TEMPLATE = TEMPLATES / "base.html"

STYLE_ATTR = re.compile(r"\sstyle\s*=", re.IGNORECASE)
STYLE_BLOCK = re.compile(r"<style(?:\s|>)", re.IGNORECASE)
EVENT_HANDLER = re.compile(r"\son[a-z]+\s*=", re.IGNORECASE)


def est_artefact_non_web(path: Path) -> bool:
    relatif = path.relative_to(TEMPLATES)
    dossiers = {partie.lower() for partie in relatif.parts[:-1]}
    nom = relatif.name.lower()
    return "emails" in dossiers or "pdf" in dossiers or nom.endswith("_email.html") or nom.endswith("_pdf.html")


def styles_inline_generes_par_python() -> list[str]:
    """Repère les ``attrs`` de widgets qui produiraient un attribut style."""
    erreurs: list[str] = []
    for path in sorted(APPS.rglob("*.py")):
        if "migrations" in path.parts or path.name.startswith("test_") or path.name in {"tests.py", "conftest.py"}:
            continue
        arbre = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for appel in (noeud for noeud in ast.walk(arbre) if isinstance(noeud, ast.Call)):
            for mot_cle in appel.keywords:
                if mot_cle.arg != "attrs" or not isinstance(mot_cle.value, ast.Dict):
                    continue
                for cle in mot_cle.value.keys:
                    if isinstance(cle, ast.Constant) and isinstance(cle.value, str) and cle.value.lower() == "style":
                        relatif = path.relative_to(RACINE)
                        erreurs.append(f"{relatif}:{appel.lineno}: attribut style interdit dans attrs=")
    return erreurs


def main() -> int:
    erreurs: list[str] = []

    for path in sorted(TEMPLATES.rglob("*.html")):
        if est_artefact_non_web(path):
            continue
        texte = path.read_text(encoding="utf-8")
        relatif = path.relative_to(RACINE)
        if STYLE_ATTR.search(texte):
            erreurs.append(f"{relatif}: attribut style= interdit")
        if STYLE_BLOCK.search(texte):
            erreurs.append(f"{relatif}: bloc <style> interdit")
        if "csp-style-" in texte:
            erreurs.append(f"{relatif}: classe de migration csp-style-* interdite")
        if EVENT_HANDLER.search(texte):
            erreurs.append(f"{relatif}: gestionnaire JavaScript inline on...= interdit")

    erreurs.extend(styles_inline_generes_par_python())

    settings = BASE.read_text(encoding="utf-8")
    attendu = {
        '"style-src": ["\'self\'"]': "style-src doit être limité à self",
        '"style-src-attr": ["\'none\'"]': "style-src-attr doit interdire les styles inline",
    }
    for fragment, message in attendu.items():
        if fragment not in settings:
            erreurs.append(f"config/settings/base.py: {message}")
    if '"style-src": ["\'self\'", "\'unsafe-inline\'"]' in settings:
        erreurs.append("config/settings/base.py: unsafe-inline réintroduit dans style-src")

    base_html = BASE_TEMPLATE.read_text(encoding="utf-8")
    if '"allowEval":false' not in base_html:
        erreurs.append("templates/base.html: HTMX allowEval doit rester à false")
    if '"allowScriptTags":false' not in base_html:
        erreurs.append("templates/base.html: HTMX allowScriptTags doit rester à false")

    if erreurs:
        print("Invariants CSP non respectés :")
        for erreur in erreurs:
            print(f"- {erreur}")
        return 1

    print("OK — pages web sans styles/scripts inline et CSP stricte maintenue.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
