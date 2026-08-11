"""Validation serveur des défis Cloudflare Turnstile.

Le widget navigateur ne constitue pas une preuve : le jeton doit être envoyé à
Siteverify avant tout traitement du formulaire. Ce service garde cette règle
dans un seul endroit et échoue fermé dès que la protection est activée.
"""

import ipaddress
import logging
from uuid import uuid4

import requests
from django.conf import settings
from requests.exceptions import RequestException, Timeout

SITEVERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
MESSAGE_ECHEC = "La vérification de sécurité a échoué. Actualisez la page et réessayez."
LONGUEUR_JETON_MAX = 2048

logger = logging.getLogger(__name__)


def est_active() -> bool:
    """La protection n'est active que si l'exploitation l'a explicitement configurée."""
    return bool(getattr(settings, "CLOUDFLARE_TURNSTILE_ENABLED", False))


def valider_requete(request, *, action: str) -> bool:
    """Valide le jeton Turnstile d'une requête POST pour une action donnée."""
    if not est_active():
        return True
    if request is None:
        logger.warning("Turnstile refuse une validation sans requête (action=%s).", action)
        return False

    jeton = request.POST.get("cf-turnstile-response", "")
    if not isinstance(jeton, str) or not jeton or len(jeton) > LONGUEUR_JETON_MAX:
        logger.info("Jeton Turnstile refusé — absent ou mal formé (action=%s).", action)
        return False

    hote_attendu = request.get_host().partition(":")[0].lower()
    donnees = {
        "secret": settings.CLOUDFLARE_TURNSTILE_SECRET_KEY,
        "response": jeton,
        "idempotency_key": str(uuid4()),
    }
    adresse_ip = _adresse_ip(request)
    if adresse_ip:
        donnees["remoteip"] = adresse_ip

    for tentative in (1, 2):
        try:
            reponse = requests.post(
                SITEVERIFY_URL,
                data=donnees,
                timeout=settings.CLOUDFLARE_TURNSTILE_TIMEOUT,
            )
            reponse.raise_for_status()
            resultat = reponse.json()
            break
        except Timeout:
            if tentative == 1:
                # Siteverify accepte la clé d'idempotence : le même contrôle
                # peut être retenté sans valider deux fois une soumission.
                logger.info(
                    "Délai Turnstile dépassé — nouvelle tentative (action=%s).",
                    action,
                )
                continue
            # Un délai d'un service tiers est une défaillance attendue et déjà
            # traitée (refus fermé). Ne pas joindre exc_info : Sentry ne doit
            # pas transformer chaque incident réseau transitoire en exception.
            logger.warning(
                "Vérification Turnstile impossible — délai Siteverify dépassé après deux tentatives "
                "(action=%s). Voir le §5 du runbook.",
                action,
            )
            return False
        except (RequestException, ValueError, TypeError):
            # Deux causes mènent au même refus, et elles n'appellent pas la même
            # réaction : un jeton rejeté est un visiteur de plus qui recommence,
            # une panne de Siteverify bloque **toutes** les connexions, personnel
            # compris. Une alerte qui ne dit pas laquelle des deux se produit
            # envoie l'exploitant chercher au mauvais endroit. D'où le niveau
            # « erreur » ici, et le libellé que le runbook fait chercher.
            logger.error(
                "Vérification Turnstile impossible — Siteverify injoignable (action=%s). "
                "Toutes les connexions sont bloquées tant que la panne dure : voir le §5 du runbook.",
                action,
                exc_info=True,
            )
            return False

    if not isinstance(resultat, dict) or not resultat.get("success"):
        codes = resultat.get("error-codes", []) if isinstance(resultat, dict) else []
        logger.info("Jeton Turnstile refusé par Siteverify (action=%s, codes=%s).", action, codes)
        return False

    if resultat.get("action") != action:
        logger.warning(
            "Turnstile refuse une action inattendue (attendue=%s, reçue=%s).",
            action,
            resultat.get("action"),
        )
        return False

    hote_recu = str(resultat.get("hostname", "")).lower()
    if hote_recu != hote_attendu:
        logger.warning(
            "Turnstile refuse un hôte inattendu (attendu=%s, reçu=%s).",
            hote_attendu,
            hote_recu,
        )
        return False

    return True


def _adresse_ip(request) -> str:
    """Adresse transmise à Siteverify, sans accepter une valeur non-IP."""
    candidate = request.META.get("HTTP_CF_CONNECTING_IP") or request.META.get("REMOTE_ADDR") or ""
    try:
        return str(ipaddress.ip_address(candidate))
    except ValueError:
        return ""
