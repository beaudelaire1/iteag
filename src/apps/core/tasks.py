"""Tâches asynchrones transverses."""

import logging
from datetime import timedelta

from django.utils import timezone

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name="core.envoyer_email")
def envoyer_email_tache(sujet: str, gabarit: str, contexte: dict, destinataires: list[str]) -> bool:
    from apps.core.services.emails import envoyer_maintenant

    return envoyer_maintenant(sujet, gabarit, contexte, destinataires)


@shared_task(name="core.purger_notifications")
def purger_notifications(jours: int = 120) -> int:
    """Supprime les notifications lues au-delà du délai de rétention."""
    from apps.core.models import Notification

    limite = timezone.now() - timedelta(days=jours)
    nombre, _ = Notification.objects.filter(lu=True, date_lecture__lt=limite).delete()
    logger.info("Purge des notifications : %s supprimée(s)", nombre)
    return nombre


@shared_task(name="core.purger_sessions")
def purger_sessions() -> int:
    """Supprime les sessions expirées de la base.

    Les sessions sont stockées en base et réécrites à chaque requête : la table
    ne se vide jamais d'elle-même, Django laissant à l'exploitant le soin
    d'appeler « clearsessions ». Sans cette tâche, « django_session » croît
    indéfiniment — un fichier de trop, jusqu'à ce qu'il pèse.
    """
    from django.contrib.sessions.models import Session
    from django.core.management import call_command
    from django.utils import timezone

    avant = Session.objects.filter(expire_date__lt=timezone.now()).count()
    call_command("clearsessions", verbosity=0)
    logger.info("Purge des sessions : %s expirée(s) supprimée(s)", avant)
    return avant


@shared_task(name="core.purger_journal_audit")
def purger_journal_audit(jours: int = 730) -> int:
    """Purge le journal d'audit au-delà de la durée de conservation (2 ans)."""
    from apps.core.models import JournalAudit

    limite = timezone.now() - timedelta(days=jours)
    nombre, _ = JournalAudit.objects.filter(created_at__lt=limite).delete()
    logger.info("Purge du journal d'audit : %s entrée(s) supprimée(s)", nombre)
    return nombre
