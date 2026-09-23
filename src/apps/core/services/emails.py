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
import smtplib
from email.mime.image import MIMEImage
from email.utils import formataddr, parseaddr
from pathlib import Path
from urllib.parse import urljoin

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.html import strip_tags

logger = logging.getLogger(__name__)


class ErreurSMTPTemporaire(RuntimeError):
    """Signale au worker qu'un relais SMTP a demandé de réessayer plus tard."""


def _est_erreur_smtp_temporaire(exc: BaseException) -> bool:
    """Les réponses SMTP 4xx sont temporaires et peuvent être rejouées sans délai humain."""
    return isinstance(exc, smtplib.SMTPResponseException) and 400 <= int(exc.smtp_code) < 500


LOGO_CID = "logo-iteag"
DOMAINE_EMAIL_SANS_MX = "@iteag.org"
SITE_CONTEXT = {
    "SITE_NAME": "ITEAG",
    "SITE_FULL_NAME": "Institut de Théologie Évangélique des Antilles et de la Guyane",
    "SITE_TAGLINE": "Une formation de qualité pour un service efficace",
    "SITE_PHONE": "+590 690 37 64 17",
    "SITE_ADDRESS": "201 lot Pointe d'Or, 97139 Les Abymes, Guadeloupe",
    "SITE_FACEBOOK": "https://fr-fr.facebook.com/iteag",
    "SITE_YOUTUBE": "https://www.youtube.com/@formationiteag327",
}


def filtrer_destinataires(adresses: list[str] | None) -> list[str]:
    """Écarte les adresses internes historiques qui ne correspondent à aucune boîte réelle.

    Le domaine iteag.org ne porte pas de messagerie. Des comptes de démonstration
    et d'anciennes données peuvent néanmoins encore contenir une adresse en
    @iteag.org. Ce garde-fou est volontairement placé au niveau du service
    d'envoi afin de couvrir tous les appelants, y compris les anciennes tâches
    Celery déjà mises en file.
    """
    valides: list[str] = []
    deja_vues: set[str] = set()
    for adresse in adresses or []:
        adresse = (adresse or "").strip()
        if not adresse:
            continue
        cle = adresse.casefold()
        if cle.endswith(DOMAINE_EMAIL_SANS_MX):
            logger.warning("Destinataire sans boîte réelle ignoré : %s", adresse)
            continue
        if cle in deja_vues:
            continue
        deja_vues.add(cle)
        valides.append(adresse)
    return valides


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
    destinataires = filtrer_destinataires(destinataires)
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


def _adresse_expediteur() -> str:
    """Construit un From cohérent avec le compte qui s'authentifie réellement."""
    brut = (getattr(settings, "DEFAULT_FROM_EMAIL", "") or "").strip()
    nom_existant, adresse = parseaddr(brut)

    # Gmail peut réécrire un From différent du compte SMTP authentifié. On ne
    # laisse donc pas deux identités contradictoires dans le même message :
    # smtp.gmail.com envoie explicitement sous EMAIL_HOST_USER.
    hote = (getattr(settings, "EMAIL_HOST", "") or "").strip().casefold()
    utilisateur_smtp = (getattr(settings, "EMAIL_HOST_USER", "") or "").strip()
    if hote == "smtp.gmail.com" and utilisateur_smtp:
        adresse = utilisateur_smtp

    if not adresse:
        return brut
    nom = nom_existant or (getattr(settings, "EMAIL_FROM_NAME", "") or "").strip()
    return formataddr((nom, adresse)) if nom else adresse


def envoyer_maintenant(
    sujet: str,
    gabarit: str,
    contexte: dict,
    destinataires: list[str],
    copie: list[str] | None = None,
    images: dict[str, str] | None = None,
    *,
    propager_erreur_smtp_temporaire: bool = False,
) -> bool:
    """Rendu et envoi immédiats. Ne lève que les erreurs SMTP temporaires demandées par Celery."""
    # Une tâche Celery peut avoir été mise en file avant un déploiement. On
    # refiltre donc ici, et pas seulement dans envoyer_email(), pour empêcher
    # une ancienne tâche d'expédier encore vers une adresse @iteag.org.
    destinataires = filtrer_destinataires(destinataires)
    copie = filtrer_destinataires(copie)
    if not destinataires:
        return False

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
        from_email=_adresse_expediteur(),
        to=destinataires,
        cc=copie or [],
        # Répondre à un avis de la plateforme doit atteindre quelqu'un, quelle
        # que soit l'adresse d'expédition que le relais SMTP impose.
        reply_to=[secretariat] if secretariat else None,
        headers={
            "Auto-Submitted": "auto-generated",
            "X-Auto-Response-Suppress": "All",
        },
    )
    message.attach_alternative(html, "text/html")
    racine_statique = Path(settings.BASE_DIR) / "static"
    pieces = []
    # N'attacher une image inline que si le HTML la référence réellement. Les
    # liens d'activation utilisent volontairement un gabarit transactionnel
    # léger : ajouter un logo MIME inutile alourdit l'empreinte antispam.
    if f"cid:{LOGO_CID}" in html and chemin_logo.exists():
        pieces.append((LOGO_CID, chemin_logo, "logo-iteag.png"))
    pieces += [
        (cid, racine_statique / relatif, Path(relatif).name)
        for cid, relatif in (images or {}).items()
        if f"cid:{cid}" in html
    ]
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
    except Exception as exc:  # noqa: BLE001
        if _est_erreur_smtp_temporaire(exc):
            logger.warning(
                "SMTP temporairement indisponible (code %s) pour « %s » ; "
                "une nouvelle tentative sera planifiée si l'envoi est asynchrone.",
                getattr(exc, "smtp_code", "?"),
                sujet,
            )
            if propager_erreur_smtp_temporaire:
                raise ErreurSMTPTemporaire(
                    f"{type(exc).__name__}: {exc}"
                ) from exc
            return False
        logger.exception("Échec d'envoi du courriel « %s » à %s", sujet, destinataires)
        return False
    return True
