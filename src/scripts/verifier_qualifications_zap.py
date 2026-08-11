"""Refuse qu'une alerte ZAP qualifiée déborde de sa surface prouvée."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from urllib.parse import urlsplit


def verifier_rapport(
    rapport: dict[str, object],
    politique: dict[str, list[str]],
    cible: str,
) -> list[str]:
    """Retourne les qualifications qui ne respectent plus l'hôte ou les chemins autorisés."""
    cible_decomposee = urlsplit(cible.rstrip("/"))
    violations: list[str] = []

    for site in rapport.get("site", []):
        if not isinstance(site, dict):
            continue
        for alerte in site.get("alerts", []):
            if not isinstance(alerte, dict):
                continue
            identifiant = str(alerte.get("pluginid", ""))
            motifs = politique.get(identifiant)
            if motifs is None:
                continue

            instances = alerte.get("instances", [])
            if not isinstance(instances, list):
                violations.append(f"ZAP {identifiant}: liste d'instances illisible.")
                continue

            for instance in instances:
                if not isinstance(instance, dict):
                    violations.append(f"ZAP {identifiant}: instance illisible.")
                    continue
                uri = str(instance.get("uri", ""))
                decomposee = urlsplit(uri)
                if (decomposee.scheme, decomposee.netloc) != (
                    cible_decomposee.scheme,
                    cible_decomposee.netloc,
                ):
                    violations.append(f"ZAP {identifiant}: hôte non qualifié {uri!r}.")
                    continue

                chemin = decomposee.path or "/"
                if decomposee.query:
                    chemin = f"{chemin}?{decomposee.query}"
                if not any(re.search(motif, chemin) for motif in motifs):
                    violations.append(f"ZAP {identifiant}: URL hors qualification {uri!r}.")

    return violations


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rapport", type=Path, required=True)
    parser.add_argument("--politique", type=Path, required=True)
    parser.add_argument("--cible", required=True)
    args = parser.parse_args()

    rapport = json.loads(args.rapport.read_text(encoding="utf-8"))
    politique = json.loads(args.politique.read_text(encoding="utf-8"))
    violations = verifier_rapport(rapport, politique, args.cible)
    if violations:
        raise SystemExit("\n".join(violations))

    print(f"Qualifications ZAP vérifiées : {len(politique)} règles, aucune URL hors politique.")


if __name__ == "__main__":
    main()
