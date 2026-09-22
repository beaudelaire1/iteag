"""Actions administratives sur un compte utilisateur.

Ces opérations n'altèrent jamais silencieusement le mot de passe : une
invitation ou une réinitialisation envoie un lien personnel au titulaire.
"""

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from apps.accounts.models import User
from apps.core.services.emails import envoyer_email

ESPACES = {
    User.Role.ADMIN: "l'espace d'administration",
    User.Role.SECRETARIAT: "l'espace secrétariat",
    User.Role.ENSEIGNANT: "l'espace enseignant",
    User.Role.ETUDIANT: "l'espace étudiant",
}


def _lien_mot_de_passe(compte: User) -> str:
    identifiant = urlsafe_base64_encode(force_bytes(compte.pk))
    jeton = default_token_generator.make_token(compte)
    chemin = reverse(
        "accounts:password_reset_confirm",
        kwargs={"uidb64": identifiant, "token": jeton},
    )
    return f"{settings.SITE_URL.rstrip('/')}{chemin}"


def renvoyer_invitation_utilisateur(compte: User) -> bool:
    """Renvoie un lien de première connexion à un compte actif et joignable."""
    if not compte.is_active or not compte.email:
        return False

    profil = getattr(compte, "profil_etudiant", None)
    return envoyer_email(
        sujet="Votre accès ITEAG",
        gabarit="administration/emails/invitation_compte.html",
        contexte={
            "prenom": compte.first_name,
            "identifiant": compte.username,
            "courriel": compte.email,
            "espace": ESPACES.get(compte.role, "votre espace"),
            "numero_etudiant": getattr(profil, "numero_etudiant", ""),
            "lien_activation": _lien_mot_de_passe(compte),
            "deja_connecte": compte.last_login is not None,
        },
        destinataires=[compte.email],
        confidentiel=True,
    )


def envoyer_reinitialisation_mot_de_passe(compte: User) -> bool:
    """Envoie un lien de réinitialisation sans modifier le mot de passe actuel."""
    if not compte.is_active or not compte.email:
        return False

    return envoyer_email(
        sujet="Réinitialisation de votre mot de passe ITEAG",
        gabarit="administration/emails/reinitialisation_mot_de_passe.html",
        contexte={
            "prenom": compte.first_name,
            "lien_reinitialisation": _lien_mot_de_passe(compte),
        },
        destinataires=[compte.email],
        confidentiel=True,
    )
