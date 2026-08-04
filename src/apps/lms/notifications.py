"""Notifications pédagogiques communes aux portails enseignant et étudiant."""

from django.contrib.auth import get_user_model

from apps.core.models import Notification
from apps.core.services.notifications import notifier, notifier_plusieurs


def details_du_cours(cours_session) -> list[dict]:
    """Cours, session et enseignant — ce qui situe n'importe quel avis de classe.

    Un même étudiant suit plusieurs cours, souvent avec des devoirs voisins :
    sans ces trois lignes, deux avis successifs sont indiscernables.
    """
    details = [{"libelle": "Cours", "valeur": cours_session.cours.titre}]
    if cours_session.session_id:
        details.append({"libelle": "Session", "valeur": str(cours_session.session)})
    if cours_session.enseignant_id:
        details.append({"libelle": "Enseignant", "valeur": str(cours_session.enseignant)})
    return details


def notifier_etudiants(
    cours_session,
    titre: str,
    *,
    message: str,
    url_cible: str,
    details: list[dict] | None = None,
    type_notification: str = Notification.Type.NOUVELLE_RESSOURCE,
) -> int:
    """Notifie uniquement les étudiants réellement inscrits au cours."""
    User = get_user_model()
    destinataires = User.objects.filter(
        is_active=True,
        profil_etudiant__inscriptions__cours_session=cours_session,
    ).distinct()
    return notifier_plusieurs(
        destinataires,
        titre,
        type_notification=type_notification,
        message=message,
        details=details if details is not None else details_du_cours(cours_session),
        url_cible=url_cible,
    )


def notifier_enseignant(cours_session, titre: str, *, message: str, url_cible: str, details=None):
    """Prévient l'enseignant lorsqu'une action étudiante requiert son attention."""
    utilisateur = getattr(cours_session.enseignant, "user", None)
    return notifier(
        utilisateur,
        titre,
        type_notification=Notification.Type.SYSTEME,
        message=message,
        details=details if details is not None else details_du_cours(cours_session),
        url_cible=url_cible,
    )
