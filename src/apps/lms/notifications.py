"""Notifications pédagogiques communes aux portails enseignant et étudiant."""

from django.contrib.auth import get_user_model

from apps.core.models import Notification
from apps.core.services.notifications import notifier, notifier_plusieurs


def notifier_etudiants(
    cours_session,
    titre: str,
    *,
    message: str,
    url_cible: str,
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
        url_cible=url_cible,
    )


def notifier_enseignant(cours_session, titre: str, *, message: str, url_cible: str):
    """Prévient l'enseignant lorsqu'une action étudiante requiert son attention."""
    utilisateur = getattr(cours_session.enseignant, "user", None)
    return notifier(
        utilisateur,
        titre,
        type_notification=Notification.Type.SYSTEME,
        message=message,
        url_cible=url_cible,
    )
