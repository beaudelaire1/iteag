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
    details: list[dict] | None = None,
    url_cible: str = "",
    envoyer_par_email: bool = True,
) -> Notification | None:
    """Crée une notification interne et son email institutionnel.

    `details` — une liste de « {libelle, valeur} » — est reprise telle quelle
    dans le courriel. C'est ce qui permet à un destinataire de savoir de quoi
    il s'agit sans se connecter : un avis qui dit « une information est
    disponible » oblige à ouvrir la plateforme pour apprendre qu'elle ne
    concernait pas le lecteur.
    """
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
        # Le courriel s'adresse à quelqu'un : le prénom seul, jamais
        # l'identifiant de connexion, qui n'a pas sa place dans un en-tête.
        prenom = (getattr(destinataire, "first_name", "") or "").strip()
        categorie = Notification.Type(type_notification).label
        transaction.on_commit(
            lambda: envoyer_notification_email(
                sujet=titre,
                titre=titre,
                message=message or titre,
                destinataires=[email],
                prenom=prenom,
                categorie=categorie,
                details=details,
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
