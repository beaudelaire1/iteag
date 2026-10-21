"""Relances groupées des premières connexions : la cadence SMTP reste centrale."""
import logging

from celery import shared_task

from apps.accounts.models import User
from apps.administration.services.comptes import (
    identifiants_relance_premiere_connexion,
    renvoyer_invitation_utilisateur,
)
from apps.core.services.audit import journaliser

logger = logging.getLogger(__name__)


@shared_task(name="administration.relancer_invitations_premiere_connexion")
def relancer_invitations_premiere_connexion(identifiants: list[int], auteur_id: int) -> dict:
    """Publie des invitations individuelles dans la file e-mail déjà limitée à 6/min.

    On ne délègue pas un SMTP massif : chaque invitation passe par le service
    existant (gabarit personnel, lien de choix de mot de passe, contrôle SMTP,
    reprise des erreurs temporaires et limitation de débit).
    """
    auteur = User.objects.filter(pk=auteur_id, is_active=True).first()
    if auteur is None or (auteur.role not in (User.Role.ADMIN, User.Role.SECRETARIAT) and not auteur.is_superuser):
        logger.warning("Relance groupée abandonnée : demandeur non autorisé (id=%s)", auteur_id)
        return {"programmes": 0, "ignores": len(identifiants), "echecs": 0}

    programmes = 0
    ignores = 0
    echecs = 0
    for identifiant in dict.fromkeys(identifiants):
        compte = User.objects.filter(pk=identifiant).first()
        if compte is None or not identifiants_relance_premiere_connexion(User.objects.filter(pk=identifiant), auteur):
            ignores += 1
            continue
        try:
            if renvoyer_invitation_utilisateur(compte):
                programmes += 1
            else:
                echecs += 1
        except Exception:  # noqa: BLE001 — poursuivre les autres destinataires sans masquer l'incident
            logger.exception("Echec de programmation de l'invitation utilisateur id=%s", identifiant)
            echecs += 1

    journaliser(
        "modification",
        utilisateur=auteur,
        objet_type="Utilisateurs",
        objet_libelle="Relance groupée des premières connexions",
        operation="relance_invitations_executee",
        nombre_programmes=programmes,
        nombre_ignores=ignores,
        nombre_echecs=echecs,
    )
    return {"programmes": programmes, "ignores": ignores, "echecs": echecs}
