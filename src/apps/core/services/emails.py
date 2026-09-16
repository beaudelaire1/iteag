"""Service d'envoi de courriels.

Tous les envois de la plateforme passent par ici : un seul endroit décide du
gabarit, de l'expéditeur, des copies et du mode d'envoi (synchrone ou différé).

Règle de copie : tout courriel adressé à la boîte du secrétariat part aussi, en
copie, à la boîte de contact de l'institut. Elle est appliquée ici plutôt que
par chaque appelant — formulaire de contact, candidatures, demandes d'accès —
parce qu'un appelant oublié serait un message que la copie ne reçoit jamais,
sans que rien ne le signale. Seuls les envois confidentiels (un lien de
définition de mot de passe) y échappent.
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
    "SITE_PHONE": "+590 690 37 64 17",
    "SITE_ADDRESS": "201 lot Pointe d'Or, 97139 Les Abymes, Guadeloupe",
    "SITE_FACEBOOK": "https://fr-fr.facebook.com/iteag",
    "SITE_YOUTUBE": "https://www.youtube.com/@formationiteag327",
}


def adresses_en_copie(destinataires: list[str]) -> list[str]:
    """Copie due à un envoi : la boîte de contact dès que le secrétariat est destinataire."""
    secretariat = (getattr(settings, "ITEAG_COURRIEL_SECRETARIAT", "") or "").casefold()
    copie = (getattr(settings, "ITEAG_COURRIEL_COPIE", "") or "").strip()
    deja_servies = {d.casefold() for d in destinataires}
    if not secretariat or not copie or secretariat not in deja_servies or copie.casefold() in deja_servies:
        return []
    return [copie]


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
    confidentiel: bool = False,
    images: dict[str, str] | None = None,
) -> bool:
    """Envoie un courriel construit à partir d'un gabarit HTML.

    `differe` confie l'envoi à Celery. En cas d'indisponibilité du courtier,
    l'envoi bascule en synchrone plutôt que d'être perdu.

    `confidentiel` supprime la copie automatique : un lien qui ouvre un compte
    ne doit arriver que dans la boîte de son titulaire.

    `images` associe un identifiant de contenu (« cid: » dans le gabarit) à un
    fichier sous `static/`. Les images sont jointes au message plutôt que
    chargées depuis le site : Orange ou Outlook bloquent les images distantes
    par défaut, et un guide illustré sans ses illustrations n'explique rien.
    """
    destinataires = [d for d in destinataires if d]
    if not destinataires:
        return False
    copie = [] if confidentiel else adresses_en_copie(destinataires)

    if differe and getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False):
        return envoyer_maintenant(sujet, gabarit, contexte, destinataires, copie, images)

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
                # La copie n'est ajoutée qu'au besoin : un message déjà en file
                # au moment d'un déploiement garde la forme qu'il avait.
                envoyer_email_tache.apply_async(
                    args=[sujet, gabarit, contexte, destinataires, *([copie] if copie else [])],
                    **({"kwargs": {"images": images}} if images else {}),
                    connection=connexion,
                    retry=False,
                )
            return True
        except Exception:  # noqa: BLE001 — courtier indisponible : on n'abandonne pas l'envoi
            logger.warning("Courtier Celery indisponible, bascule en envoi synchrone", exc_info=True)

    return envoyer_maintenant(sujet, gabarit, contexte, destinataires, copie, images)


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


def envoyer_maintenant(
    sujet: str,
    gabarit: str,
    contexte: dict,
    destinataires: list[str],
    copie: list[str] | None = None,
    images: dict[str, str] | None = None,
) -> bool:
    """Rendu et envoi immédiats. Ne lève pas : un courriel perdu n'arrête pas un workflow."""
    chemin_logo = _chemin_logo()
    secretariat = getattr(settings, "ITEAG_COURRIEL_SECRETARIAT", "")
    contexte = {
        **SITE_CONTEXT,
        "SITE_EMAIL": secretariat,
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
        cc=copie or [],
        # Répondre à un avis de la plateforme doit atteindre quelqu'un, quelle
        # que soit l'adresse d'expédition que le relais SMTP impose.
        reply_to=[secretariat] if secretariat else None,
    )
    message.attach_alternative(html, "text/html")
    racine_statique = Path(settings.BASE_DIR) / "static"
    pieces = [(LOGO_CID, chemin_logo, "logo-iteag.png")]
    pieces += [(cid, racine_statique / relatif, Path(relatif).name) for cid, relatif in (images or {}).items()]
    pieces = [piece for piece in pieces if piece[1].exists()]
    if pieces:
        message.mixed_subtype = "related"
    for cid, chemin, nom in pieces:
        image = MIMEImage(chemin.read_bytes(), _subtype="png")
        image.add_header("Content-ID", f"<{cid}>")
        image.add_header("Content-Disposition", "inline", filename=nom)
        message.attach(image)
    try:
        message.send(fail_silently=False)
    except Exception:  # noqa: BLE001
        logger.exception("Échec d'envoi du courriel « %s » à %s", sujet, destinataires)
        return False
    return True
