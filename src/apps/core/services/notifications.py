"""Service de notification interne.

Point d'entrée unique : aucune vue ne crée de Notification directement, afin que
la règle « ne pas notifier un compte inactif » et le comptage restent en un seul
endroit.
"""

from django.db import transaction
from django.db.models import QuerySet

from apps.core.models import Notification
from apps.core.services.emails import envoyer_notification_email


def notifier(
    destinataire,
    titre: str,
    *,
    type_notification: str = Notification.Type.SYSTEME,
    message: str = "",
    url_cible: str = "",
    envoyer_par_email: bool = True,
) -> Notification | None:
    """Crée une notification interne et son email institutionnel."""
    if destinataire is None or not getattr(destinataire, "is_active", False):
        return None
    notification = Notification.objects.create(
        destinataire=destinataire,
        titre=titre,
        type_notification=type_notification,
        message=message,
        url_cible=url_cible,
    )
    email = getattr(destinataire, "email", "")
    if envoyer_par_email and email:
        transaction.on_commit(
            lambda: envoyer_notification_email(
                sujet=titre,
                titre=titre,
                message=message or titre,
                destinataires=[email],
                lien=url_cible,
            )
        )
    return notification


def notifier_plusieurs(destinataires, titre: str, **kwargs) -> int:
    """Notifie un ensemble d'utilisateurs. Retourne le nombre d'envois effectifs."""
    return sum(1 for u in destinataires if notifier(u, titre, **kwargs) is not None)


def non_lues(utilisateur) -> QuerySet[Notification]:
    if not getattr(utilisateur, "is_authenticated", False):
        return Notification.objects.none()
    return Notification.objects.filter(destinataire=utilisateur, lu=False)


def compter_non_lues(utilisateur) -> int:
    return non_lues(utilisateur).count()


def marquer_tout_lu(utilisateur) -> int:
    from django.utils import timezone

    return non_lues(utilisateur).update(lu=True, date_lecture=timezone.now())
