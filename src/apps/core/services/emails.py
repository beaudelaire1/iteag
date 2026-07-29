"""Service d'envoi de courriels.

Tous les envois de la plateforme passent par ici : un seul endroit décide du
gabarit, de l'expéditeur et du mode d'envoi (synchrone ou différé).
"""

import logging
from urllib.parse import urljoin

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags

logger = logging.getLogger(__name__)


def envoyer_email(
    *,
    sujet: str,
    gabarit: str,
    contexte: dict,
    destinataires: list[str],
    differe: bool = True,
) -> bool:
    """Envoie un courriel construit à partir d'un gabarit HTML.

    `differe` confie l'envoi à Celery. En cas d'indisponibilité du courtier,
    l'envoi bascule en synchrone plutôt que d'être perdu.
    """
    destinataires = [d for d in destinataires if d]
    if not destinataires:
        return False

    if differe and getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False):
        return envoyer_maintenant(sujet, gabarit, contexte, destinataires)

    if differe:
        from apps.core.tasks import envoyer_email_tache

        try:
            envoyer_email_tache.delay(sujet, gabarit, contexte, destinataires)
            return True
        except Exception:  # noqa: BLE001 — courtier indisponible : on n'abandonne pas l'envoi
            logger.warning("Courtier Celery indisponible, bascule en envoi synchrone", exc_info=True)

    return envoyer_maintenant(sujet, gabarit, contexte, destinataires)


def envoyer_notification_email(
    *,
    sujet: str,
    titre: str,
    message: str,
    destinataires: list[str],
    lien: str = "",
    libelle_lien: str = "Consulter dans mon espace",
    differe: bool = True,
) -> bool:
    """Envoie une information métier avec le gabarit institutionnel ITEAG."""
    if lien and not lien.startswith(("http://", "https://")):
        lien = urljoin(f"{settings.SITE_URL.rstrip('/')}/", lien.lstrip("/"))
    return envoyer_email(
        sujet=sujet,
        gabarit="core/emails/notification.html",
        contexte={
            "titre": titre,
            "message": message,
            "lien": lien,
            "libelle_lien": libelle_lien,
        },
        destinataires=destinataires,
        differe=differe,
    )


def envoyer_maintenant(sujet: str, gabarit: str, contexte: dict, destinataires: list[str]) -> bool:
    """Rendu et envoi immédiats. Ne lève pas : un courriel perdu n'arrête pas un workflow."""
    contexte = {
        "SITE_NAME": "ITEAG",
        "SITE_URL": getattr(settings, "SITE_URL", ""),
        **contexte,
    }
    try:
        html = render_to_string(gabarit, contexte)
    except Exception:  # noqa: BLE001
        logger.exception("Gabarit d'email introuvable ou invalide : %s", gabarit)
        return False

    message = EmailMultiAlternatives(
        subject=f"[ITEAG] {sujet}",
        body=strip_tags(html),
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=destinataires,
    )
    message.attach_alternative(html, "text/html")
    try:
        message.send(fail_silently=False)
    except Exception:  # noqa: BLE001
        logger.exception("Échec d'envoi du courriel « %s » à %s", sujet, destinataires)
        return False
    return True
