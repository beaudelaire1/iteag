"""Métadonnées éditoriales Bunny Stream utilisées par le lecteur ITEAG.

Le chemin critique de lecture ne dépend pas de l'API Bunny : le HLS reste signé
localement. Cet appel ne sert qu'à enrichir l'interface avec les chapitres que
Bunny a générés (notamment via Smart Chapters) et il est mis en cache.
"""

import json
import logging
import os
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from django.core.cache import cache

logger = logging.getLogger(__name__)

CACHE_CHAPITRES_SECONDES = 15 * 60
TIMEOUT_BUNNY_SECONDES = 3


def _configuration() -> tuple[str, str]:
    """Retourne l'identifiant de bibliothèque et la clé API, sans les exposer."""
    return (
        os.environ.get("BUNNY_STREAM_LIBRARY_ID", "").strip(),
        os.environ.get("BUNNY_STREAM_API_KEY", "").strip(),
    )


def _normaliser_chapitres(brut) -> list[dict]:
    chapitres = []
    for entree in brut or []:
        if not isinstance(entree, dict):
            continue
        titre = str(entree.get("title") or "").strip()
        try:
            debut = max(0, int(float(entree.get("start", 0) or 0)))
            fin = max(0, int(float(entree.get("end", 0) or 0)))
        except (TypeError, ValueError):
            continue
        if not titre or fin <= debut:
            continue
        chapitres.append({"titre": titre[:200], "debut": debut, "fin": fin})

    chapitres.sort(key=lambda chapitre: (chapitre["debut"], chapitre["fin"]))
    return chapitres[:100]


def chapitres_video(identifiant_video: str) -> list[dict]:
    """Lit les chapitres Bunny, avec cache et repli silencieux.

    L'absence de clé API ne doit jamais empêcher une vidéo de démarrer : dans ce
    cas le lecteur conserve ses miniatures de seek, mais n'affiche simplement
    pas de marqueurs de chapitres.
    """
    identifiant = str(identifiant_video or "").strip()
    bibliotheque, cle_api = _configuration()
    if not identifiant or not bibliotheque or not cle_api:
        return []

    cache_key = f"elearning:bunny:chapitres:{bibliotheque}:{identifiant}"
    memorise = cache.get(cache_key)
    if memorise is not None:
        return memorise

    url = (
        "https://video.bunnycdn.com/library/"
        f"{quote(bibliotheque, safe='')}/videos/{quote(identifiant, safe='')}"
    )
    requete = Request(
        url,
        headers={
            "AccessKey": cle_api,
            "Accept": "application/json",
            "User-Agent": "ITEAG/1.0",
        },
    )

    try:
        with urlopen(requete, timeout=TIMEOUT_BUNNY_SECONDES) as reponse:  # noqa: S310 — domaine Bunny fixé ci-dessus
            charge = json.loads(reponse.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, UnicodeDecodeError, OSError):
        logger.warning("Métadonnées Bunny indisponibles pour la vidéo %s", identifiant, exc_info=True)
        return []

    chapitres = _normaliser_chapitres(charge.get("chapters") if isinstance(charge, dict) else None)
    cache.set(cache_key, chapitres, CACHE_CHAPITRES_SECONDES)
    return chapitres
