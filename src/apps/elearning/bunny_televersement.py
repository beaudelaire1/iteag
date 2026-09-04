"""
Dépôt d'une vidéo sur Bunny Stream depuis la plateforme.

Jusqu'ici, une vidéo se référençait : l'enseignant la déposait lui-même chez le
fournisseur, puis recopiait le lien. Le média ne transitait jamais par le serveur
de l'institut — c'est encore le cas du référencement, et ce module ne le change
pas.

Il ouvre une seconde voie, pour l'enseignant qui n'a pas de compte Bunny et n'a
pas à en avoir un : le fichier passe par ITEAG, qui le pousse chez Bunny avec sa
propre clé. Le média transite donc, et c'est assumé — le prix d'un dépôt en un
geste, pour un institut qui publie quelques vidéos par semaine.

Bunny reste le seul fournisseur ouvert au dépôt. YouTube et Vimeo sont déclarés
« contenu public » par le modèle de diffusion, qui refuse de les rattacher à un
module restreint : leur proposer ici laisserait croire qu'une vidéo de cours peut
y vivre, alors qu'un lien YouTube ne se révoque pas.
"""

import json
import logging
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings

logger = logging.getLogger(__name__)

RACINE_API = "https://video.bunnycdn.com/library"

# La création et la lecture d'état sont de petits appels ; l'envoi du fichier
# occupe la connexion le temps du transfert, et une vidéo de vingt minutes pèse
# plusieurs centaines de mégaoctets.
TIMEOUT_APPEL_SECONDES = 15
TIMEOUT_ENVOI_SECONDES = 30 * 60

# Codes d'état Bunny. Seuls « terminé » et « résolution terminée » valent prêt :
# une vidéo encore en file d'attente est lisible par personne.
ETAT_EN_ATTENTE = 0
ETAT_TRAITEMENT = 1
ETAT_ENCODAGE = 2
ETAT_TERMINE = 3
ETAT_RESOLUTION_TERMINEE = 4
ETAT_ECHEC = 5


class TeleversementBunnyIndisponible(RuntimeError):
    """Bunny n'est pas joignable, ou la plateforme n'est pas configurée pour lui."""


def televersement_disponible() -> bool:
    """Le dépôt exige la clé d'API, que la simple lecture ne réclame pas.

    Sans elle, l'écran doit proposer le référencement seul plutôt qu'un
    formulaire qui échouerait à l'envoi.
    """
    return bool(_configuration(silencieux=True))


def _configuration(*, silencieux: bool = False) -> tuple[str, str] | None:
    bibliotheque = str(getattr(settings, "BUNNY_STREAM_LIBRARY_ID", "") or "").strip()
    cle = str(getattr(settings, "BUNNY_STREAM_API_KEY", "") or "").strip()
    if bibliotheque and cle:
        return bibliotheque, cle
    if silencieux:
        return None
    raise TeleversementBunnyIndisponible(
        "Le dépôt de vidéos exige BUNNY_STREAM_LIBRARY_ID et BUNNY_STREAM_API_KEY."
    )


def _appeler(url: str, *, cle: str, methode: str, corps=None, entetes=None, timeout: int):
    requete = Request(url, data=corps, method=methode)  # noqa: S310 — hôte fixe, HTTPS
    requete.add_header("AccessKey", cle)
    requete.add_header("Accept", "application/json")
    for nom, valeur in (entetes or {}).items():
        requete.add_header(nom, valeur)

    try:
        with urlopen(requete, timeout=timeout) as reponse:  # noqa: S310 — hôte fixe, HTTPS
            charge = reponse.read()
    except HTTPError as erreur:
        # Le corps d'erreur de Bunny nomme la cause — bibliothèque inconnue, clé
        # refusée, quota. Le perdre laisserait « HTTP 401 » comme seul indice.
        detail = ""
        try:
            detail = erreur.read().decode("utf-8", "replace")[:300]
        except Exception:  # noqa: BLE001 — le détail est un confort, jamais requis
            pass
        raise TeleversementBunnyIndisponible(f"Bunny a refusé l'appel ({erreur.code}). {detail}".strip()) from erreur
    except (URLError, TimeoutError) as erreur:
        raise TeleversementBunnyIndisponible(f"Bunny est injoignable : {erreur}") from erreur

    if not charge:
        return {}
    try:
        return json.loads(charge.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as erreur:
        raise TeleversementBunnyIndisponible("Réponse Bunny illisible.") from erreur


def creer_video(titre: str) -> str:
    """Déclare la vidéo chez Bunny et retourne son identifiant.

    L'identifiant existe avant que le fichier ne parte : c'est lui qui recevra
    l'envoi, et c'est lui qu'on enregistre pour retrouver la vidéo même si le
    transfert échoue ensuite.
    """
    bibliotheque, cle = _configuration()
    corps = json.dumps({"title": titre[:250]}).encode("utf-8")
    reponse = _appeler(
        f"{RACINE_API}/{bibliotheque}/videos",
        cle=cle,
        methode="POST",
        corps=corps,
        entetes={"Content-Type": "application/json"},
        timeout=TIMEOUT_APPEL_SECONDES,
    )
    identifiant = str(reponse.get("guid") or "").strip()
    if not identifiant:
        raise TeleversementBunnyIndisponible("Bunny n'a pas retourné d'identifiant de vidéo.")
    return identifiant


def envoyer_fichier(identifiant: str, fichier, taille: int) -> None:
    """Pousse le contenu vers la vidéo déjà déclarée.

    Le fichier est transmis tel quel, sans être lu en mémoire : une vidéo de
    plusieurs centaines de mégaoctets ne doit pas tenir dans le worker.
    """
    bibliotheque, cle = _configuration()
    _appeler(
        f"{RACINE_API}/{bibliotheque}/videos/{identifiant}",
        cle=cle,
        methode="PUT",
        corps=fichier,
        entetes={"Content-Type": "application/octet-stream", "Content-Length": str(taille)},
        timeout=TIMEOUT_ENVOI_SECONDES,
    )


def etat_video(identifiant: str) -> int:
    """Code d'état Bunny, ou ÉTAT_ÉCHEC si la réponse ne dit rien d'exploitable."""
    bibliotheque, cle = _configuration()
    reponse = _appeler(
        f"{RACINE_API}/{bibliotheque}/videos/{identifiant}",
        cle=cle,
        methode="GET",
        timeout=TIMEOUT_APPEL_SECONDES,
    )
    try:
        return int(reponse.get("status"))
    except (TypeError, ValueError):
        return ETAT_ECHEC


def duree_video(identifiant: str) -> int:
    """Durée en secondes telle que Bunny l'a mesurée après encodage."""
    bibliotheque, cle = _configuration()
    reponse = _appeler(
        f"{RACINE_API}/{bibliotheque}/videos/{identifiant}",
        cle=cle,
        methode="GET",
        timeout=TIMEOUT_APPEL_SECONDES,
    )
    try:
        return max(0, int(float(reponse.get("length") or 0)))
    except (TypeError, ValueError):
        return 0
