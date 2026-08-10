#!/usr/bin/env python3
"""Prouve qu'un audit live vise la révision réellement attendue.

Le script ne se contente pas de vérifier qu'une URL répond. Il attend que la
préproduction serve exactement ``--revision`` puis contrôle les deux invariants
SEO qui dépendent de l'hôte réel : canonical de l'accueil et unicité de l'hôte
du sitemap.

Il est volontairement sans dépendance tierce afin de pouvoir tourner dans
GitHub Actions comme depuis un poste d'exploitation.
"""

from __future__ import annotations

import argparse
import re
import sys
import time
import urllib.error
import urllib.request
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree

ENTETE_REVISION = "X-ITEAG-Revision"
ENTETES = {"User-Agent": "ITEAG-Predeploy-Revision-Gate/1.0"}


class CanonicalParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.canonical = ""

    def handle_starttag(self, tag, attrs):
        if tag != "link":
            return
        data = {str(cle).lower(): valeur for cle, valeur in attrs if cle}
        rel = {morceau.lower() for morceau in str(data.get("rel") or "").split()}
        if "canonical" in rel:
            self.canonical = str(data.get("href") or "").strip()


def lire(url: str, *, timeout: float = 20.0):
    requete = urllib.request.Request(url, headers=ENTETES)
    with urllib.request.urlopen(requete, timeout=timeout) as reponse:
        return reponse.status, reponse.headers, reponse.read()


def attendre_revision(base: str, attendue: str, *, attente: int, intervalle: int) -> None:
    """Attend le redéploiement Coolify sans pouvoir valider l'ancienne version."""
    echeance = time.monotonic() + attente
    derniere = "aucune"
    derniere_erreur = ""

    while True:
        try:
            code, entetes, _ = lire(urljoin(base, "healthz"))
            derniere = (entetes.get(ENTETE_REVISION) or "").strip() or "absente"
            if code == 200 and derniere == attendue:
                print(f"Révision déployée vérifiée : {derniere}")
                return
            derniere_erreur = f"HTTP {code}, révision {derniere}"
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            derniere_erreur = str(exc)

        if time.monotonic() >= echeance:
            raise SystemExit(
                "La préproduction n'a pas servi la révision attendue dans le délai imparti : "
                f"attendue={attendue}, dernière={derniere}, détail={derniere_erreur}."
            )
        print(
            f"Préproduction pas encore alignée : attendue={attendue}, "
            f"observée={derniere} ({derniere_erreur}). Nouvelle vérification dans {intervalle}s."
        )
        time.sleep(intervalle)


def verifier_canonical(base: str) -> None:
    code, _, corps = lire(base)
    if code != 200:
        raise SystemExit(f"Accueil préproduction -> HTTP {code}.")

    parseur = CanonicalParser()
    parseur.feed(corps.decode("utf-8", errors="replace"))
    attendu = base
    if parseur.canonical != attendu:
        raise SystemExit(f"Canonical incohérente : {parseur.canonical!r}, attendu {attendu!r}.")
    print(f"Canonical vérifiée : {parseur.canonical}")


def verifier_sitemap(base: str) -> None:
    code, _, corps = lire(urljoin(base, "sitemap.xml"), timeout=30)
    if code != 200:
        raise SystemExit(f"Sitemap préproduction -> HTTP {code}.")
    try:
        racine = ElementTree.fromstring(corps)
    except ElementTree.ParseError as exc:
        raise SystemExit(f"Sitemap XML invalide : {exc}") from exc

    urls = [elt.text.strip() for elt in racine.iter() if elt.tag.endswith("loc") and elt.text and elt.text.strip()]
    if not urls:
        raise SystemExit("Sitemap vide.")

    hote_attendu = urlparse(base).netloc
    hotes = {urlparse(url).netloc for url in urls}
    if hotes != {hote_attendu}:
        raise SystemExit(f"Le sitemap mélange des hôtes : {sorted(hotes)}, attendu uniquement {hote_attendu}.")
    if any(not re.match(r"^https://", url) for url in urls):
        raise SystemExit("Le sitemap contient au moins une URL non HTTPS.")
    print(f"Sitemap vérifié : {len(urls)} URL, hôte unique {hote_attendu}.")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--revision", required=True, help="SHA Git complet attendu")
    parser.add_argument("--attente", type=int, default=600, help="secondes maximales d'attente du redéploiement")
    parser.add_argument("--intervalle", type=int, default=15)
    args = parser.parse_args()

    base = args.base_url.rstrip("/") + "/"
    revision = args.revision.strip()
    if not re.fullmatch(r"[0-9a-fA-F]{40}", revision):
        raise SystemExit(f"Révision attendue invalide : {revision!r}.")

    attendre_revision(base, revision, attente=max(args.attente, 0), intervalle=max(args.intervalle, 1))
    verifier_canonical(base)
    verifier_sitemap(base)
    return 0


if __name__ == "__main__":
    sys.exit(main())
