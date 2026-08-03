"""Alerte de sécurité sur modification d'une information sensible.

Un changement de coordonnées est le premier geste d'une prise de compte : on
détourne l'adresse électronique ou le téléphone, puis on demande une
réinitialisation de mot de passe. Le titulaire doit donc l'apprendre par un
canal qui ne dépend pas de la valeur qui vient de changer — d'où l'envoi à
l'ancienne adresse autant qu'à la nouvelle.
"""

from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from apps.core.models import Notification
from apps.core.services.emails import envoyer_notification_email
from apps.core.services.notifications import notifier

# Libellé et accord du participe : « votre adresse a été modifiée ».
CHAMPS_SURVEILLES: dict[str, tuple[str, str]] = {
    "username": ("votre identifiant de connexion", "modifié"),
    "email": ("votre adresse électronique", "modifiée"),
    "phone": ("votre numéro de téléphone", "modifié"),
    "adresse": ("votre adresse postale", "modifiée"),
    "complement_adresse": ("le complément de votre adresse", "modifié"),
    "code_postal": ("votre code postal", "modifié"),
    "ville": ("votre ville", "modifiée"),
    "pays": ("votre pays", "modifié"),
}

_CONSIGNE = (
    "Si vous n'êtes pas à l'origine de ce changement, réinitialisez immédiatement "
    "votre mot de passe et prévenez le secrétariat."
)


def etat_sensible(utilisateur) -> dict[str, str]:
    """Photographie des champs surveillés, à prendre avant toute validation."""
    return {champ: (getattr(utilisateur, champ, "") or "") for champ in CHAMPS_SURVEILLES}


def alerter_du_changement(utilisateur, avant: dict[str, str], *, auteur=None) -> dict[str, tuple[str, str]]:
    """Prévient le titulaire des champs qui ont changé. Retourne le détail des écarts."""
    apres = etat_sensible(utilisateur)
    modifications = {
        champ: (avant.get(champ, ""), apres[champ])
        for champ in CHAMPS_SURVEILLES
        if avant.get(champ, "") != apres[champ]
    }
    if not modifications:
        return {}

    titre = _titre(modifications)
    detail = [
        f"— {CHAMPS_SURVEILLES[c][0].capitalize()} : {_valeur(a)} → {_valeur(b)}" for c, (a, b) in modifications.items()
    ]
    message = "\n".join([f"{titre} {_quand()}{_par(utilisateur, auteur)}.", "", *detail, "", _CONSIGNE])
    # L'ancienne adresse est le seul canal encore sous contrôle du titulaire si
    # c'est précisément l'adresse que l'on vient de lui changer.
    _alerter(utilisateur, titre, message, adresses=[apres["email"], avant.get("email", "")])
    return modifications


def alerter_du_mot_de_passe(utilisateur, *, auteur=None) -> None:
    """Prévient le titulaire que son mot de passe a changé."""
    titre = "Votre mot de passe a été modifié"
    message = f"{titre} {_quand()}{_par(utilisateur, auteur)}.\n\n{_CONSIGNE}"
    _alerter(utilisateur, titre, message, adresses=[getattr(utilisateur, "email", "")])


def _alerter(utilisateur, titre: str, message: str, *, adresses: list[str]) -> None:
    notifier(
        utilisateur,
        titre,
        type_notification=Notification.Type.SECURITE,
        message=message,
        url_cible=reverse("accounts:profil"),
        envoyer_par_email=False,
    )
    lien = reverse("accounts:password_reset")
    for adresse in dict.fromkeys(a for a in adresses if a):
        # Un envoi par adresse : deux destinataires d'un même message se
        # découvriraient l'un l'autre en cas de saisie erronée.
        transaction.on_commit(
            lambda adresse=adresse: envoyer_notification_email(
                sujet=titre,
                titre=titre,
                message=message,
                destinataires=[adresse],
                lien=lien,
                libelle_lien="Réinitialiser mon mot de passe",
            )
        )


def _titre(modifications: dict[str, tuple[str, str]]) -> str:
    if len(modifications) == 1:
        libelle, accord = CHAMPS_SURVEILLES[next(iter(modifications))]
        return f"{libelle.capitalize()} a été {accord}"
    return "Vos informations de compte ont été modifiées"


def _quand() -> str:
    return timezone.localtime().strftime("le %d/%m/%Y à %H:%M")


def _par(utilisateur, auteur) -> str:
    if auteur is None or auteur.pk == utilisateur.pk:
        return ""
    return " depuis l'administration de l'institut"


def _valeur(brut: str) -> str:
    return brut or "(vide)"
