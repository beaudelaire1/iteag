"""
Comptes nominatifs du personnel de l'institut.

La plateforme a été livrée avec des comptes de démonstration — « secretariat_iteag »,
« direction_iteag », un compte par fiche de professeur — portant tous le même mot
de passe publié dans le dépôt, et des adresses en « @iteag.org », domaine qui ne
reçoit aucun courriel. Ce module ouvre à leur place les comptes des personnes
réelles, et referme les premiers.

Aucun mot de passe ne transite : chaque compte reçoit un secret aléatoire que
personne ne connaît, puis un lien pour choisir le sien. Le secret est
utilisable, et non « inutilisable » au sens de Django, pour une raison précise :
la réinitialisation de Django ignore les comptes sans mot de passe utilisable.
Un lien d'invitation expiré laisserait alors le titulaire sans aucun recours,
alors qu'ici « Mot de passe oublié » prend le relais.

Le secrétariat et l'administration enrôlent leur application d'authentification
à la première connexion : le middleware du second facteur l'exige avant toute
autre page (voir apps/accounts/middleware.py).
"""

import secrets
from dataclasses import dataclass

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.db import transaction
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from apps.accounts.models import User
from apps.accounts.otp import deux_facteurs_requis
from apps.core.services.emails import envoyer_email
from apps.formations.models import Professeur

# Celui de la commande « seed_comptes ». Il est public : tout compte qui le
# porte encore est ouvert à quiconque a lu le dépôt.
MOT_DE_PASSE_DEMONSTRATION = "DemoIteag!2026"
COMPTES_DE_SERVICE_DEMONSTRATION = ("secretariat_iteag", "direction_iteag")

ESPACES = {
    User.Role.SECRETARIAT: "l'espace secrétariat",
    User.Role.ENSEIGNANT: "l'espace enseignant",
    User.Role.ADMIN: "l'espace d'administration",
}


@dataclass(frozen=True)
class MembreDuPersonnel:
    identifiant: str
    prenom: str
    nom: str
    role: str
    courriel: str = ""
    # Slug de la fiche publique à rattacher, pour un enseignant.
    fiche_professeur: str = ""


PERSONNEL_ITEAG = (
    MembreDuPersonnel(
        "viviane.foucan",
        "Viviane",
        "Foucan",
        User.Role.SECRETARIAT,
        courriel="secretariat.iteag@gmail.com",
    ),
    # Directeur pédagogique, mais c'est comme professeur qu'il utilise la
    # plateforme : ses cours, ses copies, ses notes.
    MembreDuPersonnel(
        "alain.nisus",
        "Alain",
        "Nisus",
        User.Role.ENSEIGNANT,
        courriel="anisus971@gmail.com",
        fiche_professeur="alain-nisus",
    ),
    # Comptabilité et administration. Adresse connue après l'ouverture des
    # autres comptes : la migration accounts 0007 la renseigne et l'invite.
    MembreDuPersonnel(
        "patricia.alphonse",
        "Patricia",
        "Alphonse",
        User.Role.ADMIN,
        courriel="patricia.alphonse-dernault@orange.fr",
    ),
)


def installer_personnel_iteag(membres=PERSONNEL_ITEAG) -> dict[str, list[str]]:
    """Referme les comptes de démonstration, puis ouvre ceux du personnel."""
    neutralises = neutraliser_comptes_de_demonstration()
    ouverts, invites = [], []
    for membre in membres:
        compte, invitation = ouvrir_compte(membre)
        if compte is not None:
            ouverts.append(compte.username)
        if invitation:
            invites.append(compte.username)
    return {"neutralises": neutralises, "ouverts": ouverts, "invites": invites}


def neutraliser_comptes_de_demonstration() -> list[str]:
    """Retire le mot de passe public de tout compte du personnel qui le porte encore.

    Les deux comptes de service génériques sont en outre désactivés : des
    personnes nommées les remplacent. Les comptes d'enseignants restent actifs,
    rattachés à leur fiche — seul le mot de passe connu de tous disparaît.
    Rien n'est supprimé.
    """
    neutralises = []
    for compte in User.objects.filter(is_active=True).exclude(role=User.Role.ETUDIANT).order_by("pk"):
        if not _porte_le_mot_de_passe_de_demonstration(compte):
            continue
        compte.set_password(secrets.token_urlsafe(32))
        champs = ["password"]
        if compte.username in COMPTES_DE_SERVICE_DEMONSTRATION:
            compte.is_active = False
            champs.append("is_active")
        compte.save(update_fields=champs)
        neutralises.append(compte.username)
    return neutralises


@transaction.atomic
def ouvrir_compte(membre: MembreDuPersonnel) -> tuple[User | None, bool]:
    """Crée le compte, ou reprend un compte de démonstration. Retourne (compte, invitation envoyée).

    Un compte déjà pris en main — adresse réelle, mot de passe choisi — n'est
    jamais réécrit : ce qu'une personne a corrigé prime sur ce module.
    """
    fiche = Professeur.objects.filter(slug=membre.fiche_professeur).first() if membre.fiche_professeur else None
    compte = User.objects.filter(username=membre.identifiant).first()
    if compte is None and fiche is not None and fiche.user_id:
        compte = fiche.user

    if compte is not None and not _a_reprendre(compte):
        return compte, False

    if compte is None:
        compte = User(username=membre.identifiant)
    compte.first_name = membre.prenom
    compte.last_name = membre.nom
    compte.email = membre.courriel
    compte.role = membre.role
    compte.is_active = True
    compte.set_password(secrets.token_urlsafe(32))
    compte.save()

    if fiche is not None and fiche.user_id is None:
        fiche.user = compte
        fiche.save(update_fields=["user", "updated_at"])

    return compte, bool(compte.email) and inviter(compte)


def inviter(compte: User) -> bool:
    """Envoie le lien de première connexion, à son seul titulaire."""
    identifiant = urlsafe_base64_encode(force_bytes(compte.pk))
    jeton = default_token_generator.make_token(compte)
    racine = settings.SITE_URL.rstrip("/")
    lien = racine + reverse("accounts:password_reset_confirm", kwargs={"uidb64": identifiant, "token": jeton})

    return envoyer_email(
        sujet="Votre espace est ouvert",
        gabarit="administration/emails/invitation_personnel.html",
        contexte={
            "prenom": compte.first_name,
            "espace": ESPACES.get(compte.role, "votre espace"),
            "identifiant": compte.username,
            "courriel": compte.email,
            "lien_activation": lien,
            "lien_oubli": racine + reverse("accounts:password_reset"),
            "lien_connexion": racine + reverse("accounts:login"),
            "deux_facteurs": deux_facteurs_requis(compte),
            "validite_jours": max(1, settings.PASSWORD_RESET_TIMEOUT // 86400),
        },
        destinataires=[compte.email],
        # Synchrone : l'appel vient d'une migration, sans worker pour le prendre.
        differe=False,
        confidentiel=True,
    )


def _a_reprendre(compte: User) -> bool:
    """Compte encore dans son état de démonstration, sans titulaire joignable."""
    adresse = (compte.email or "").strip().casefold()
    return not adresse or adresse.endswith("@iteag.org") or _porte_le_mot_de_passe_de_demonstration(compte)


def _porte_le_mot_de_passe_de_demonstration(compte: User) -> bool:
    return compte.has_usable_password() and compte.check_password(MOT_DE_PASSE_DEMONSTRATION)
