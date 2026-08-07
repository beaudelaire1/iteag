"""Healthcheck du couple Celery Beat + worker."""

from datetime import datetime

from django.core.cache import cache
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.core.tasks import HEARTBEAT_CELERY_CACHE_KEY


class Command(BaseCommand):
    help = "Échoue si aucun heartbeat Celery récent n'a été exécuté."

    def add_arguments(self, parser):
        parser.add_argument("--max-age", type=int, default=180, help="Âge maximal accepté en secondes.")

    def handle(self, *args, **options):
        valeur = cache.get(HEARTBEAT_CELERY_CACHE_KEY)
        if not valeur:
            raise CommandError("Aucun heartbeat Celery récent.")

        try:
            instant = datetime.fromisoformat(valeur)
        except (TypeError, ValueError) as erreur:
            raise CommandError("Heartbeat Celery illisible.") from erreur

        if timezone.is_naive(instant):
            instant = timezone.make_aware(instant)
        age = (timezone.now() - instant).total_seconds()
        if age > options["max_age"]:
            raise CommandError(f"Heartbeat Celery trop ancien : {age:.0f} s.")

        self.stdout.write(self.style.SUCCESS(f"Heartbeat Celery OK ({age:.0f} s)."))
