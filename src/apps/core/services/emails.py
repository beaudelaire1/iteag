"""Service d'envoi de courriels.

Tous les envois de la plateforme passent par ici : un seul endroit décide du
gabarit, de l'expéditeur et du mode d'envoi (synchrone ou différé).
"""

import logging
from email.mime.image import MIMEImage
from pathlib import Path
from urllib.parse import urljoin

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.html import strip_tags

logger = logging.getLogger(__name__)

LOGO_CID = "logo-iteag"
SITE_CONTEXT = {
    "SITE_NAME": "ITEAG",
    "SITE_FULL_NAME": "Institut de Théologie Évangélique des Antilles et de la Guyane",
    "SITE_TAGLINE": "Une formation de qualité pour un service efficace",
    "SITE_EMAIL": "secretariat@iteag.org",
    "SITE_PHONE": "+590 690 37 64 17",
    "SITE_ADDRESS": "201 lot Pointe d'Or, 97139 Les Abymes, Guadeloupe",
    "SITE_FACEBOOK": "https://fr-fr.facebook.com/iteag",
    "SITE_YOUTUBE": "https://www.youtube.com/@formationiteag327",
}


def _chemin_logo() -> Path:
    return Path(settings.BASE_DIR) / "static" / "img" / "logo.png"


def _connexion_celery():
    """Connexion d'écriture isolée, afin de borner son acquisition."""
    from celery import current_app

    return current_app.connection_for_write()


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
            # Une publication Celery est faite pendant la requête HTTP. Les
            # reprises par défaut de Kombu peuvent la retenir plus d'une
            # minute quand Redis n'est pas lancé — cas courant en local —
            # avant d'atteindre le repli synchrone ci-dessous. Un seul essai
            # suffit : soit le courtier accepte immédiatement, soit le repli
            # garantit que le message n'est pas perdu.
            with _connexion_celery() as connexion:
                connexion.ensure_connection(
                    max_retries=0,
                    timeout=getattr(settings, "CELERY_BROKER_CONNECTION_TIMEOUT", 1.0),
                )
                envoyer_email_tache.apply_async(
                    args=[sujet, gabarit, contexte, destinataires],
                    connection=connexion,
                    retry=False,
                )
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
    prenom: str = "",
    categorie: str = "",
    details: list[dict] | None = None,
    lien: str = "",
    libelle_lien: str = "Consulter dans mon espace",
    differe: bool = True,
) -> bool:
    """Envoie une information métier avec le gabarit institutionnel ITEAG.

    `prenom` et `details` sont ce qui distingue un courrier d'un avis de
    service : le premier s'adresse à quelqu'un, le second dit de quoi il
    retourne sans obliger à se connecter pour le savoir. `details` est une
    liste de « {libelle, valeur} » — elle traverse Celery, donc rien qui ne
    soit sérialisable en JSON.
    """
    if lien and not lien.startswith(("http://", "https://")):
        lien = urljoin(f"{settings.SITE_URL.rstrip('/')}/", lien.lstrip("/"))
    return envoyer_email(
        sujet=sujet,
        gabarit="core/emails/notification.html",
        contexte={
            "titre": titre,
            "message": message,
            "prenom": prenom,
            "categorie": categorie,
            "details": details or [],
            "lien": lien,
            "libelle_lien": libelle_lien,
        },
        destinataires=destinataires,
        differe=differe,
    )


def envoyer_maintenant(sujet: str, gabarit: str, contexte: dict, destinataires: list[str]) -> bool:
    """Rendu et envoi immédiats. Ne lève pas : un courriel perdu n'arrête pas un workflow."""
    chemin_logo = _chemin_logo()
    contexte = {
        **SITE_CONTEXT,
        "SITE_URL": getattr(settings, "SITE_URL", ""),
        "ANNEE_COURANTE": timezone.now().year,
        "EMAIL_LOGO_CID": LOGO_CID if chemin_logo.exists() else "",
        **contexte,
    }
    try:
        html = render_to_string(gabarit, contexte)
    except Exception:  # noqa: BLE001
        logger.exception("Gabarit d'email introuvable ou invalide : %s", gabarit)
        return False

    message = EmailMultiAlternatives(
        # « ITEAG - » plutôt que « [ITEAG] » : des crochets dans un objet font
        # message de service automatisé, et certains filtres les pénalisent.
        subject=f"ITEAG - {sujet}",
        body=strip_tags(html),
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=destinataires,
    )
    message.attach_alternative(html, "text/html")
    if chemin_logo.exists():
        logo = MIMEImage(chemin_logo.read_bytes(), _subtype="png")
        logo.add_header("Content-ID", f"<{LOGO_CID}>")
        logo.add_header("Content-Disposition", "inline", filename="logo-iteag.png")
        message.mixed_subtype = "related"
        message.attach(logo)
    try:
        message.send(fail_silently=False)
    except Exception:  # noqa: BLE001
        logger.exception("Échec d'envoi du courriel « %s » à %s", sujet, destinataires)
        return False
    return True
