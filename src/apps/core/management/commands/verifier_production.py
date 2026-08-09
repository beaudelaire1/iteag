from django.core.management.base import BaseCommand, CommandError

from apps.core.services.production import (
    anomalies_configuration_production,
    anomalies_donnees_production,
)


class Command(BaseCommand):
    help = "Vérifie que l'instance est configurée pour une ouverture publique en production."

    def add_arguments(self, parser):
        parser.add_argument(
            "--sans-base",
            action="store_true",
            help="N'exécute que les contrôles de réglages, sans interroger la base.",
        )

    def handle(self, *args, **options):
        anomalies = anomalies_configuration_production()
        # Les contrôles en base viennent après ceux des réglages : une instance
        # dont SITE_URL est absent n'a pas d'hôte à comparer, et signaler les
        # deux ferait passer une cause pour deux problèmes.
        if not options["sans_base"]:
            anomalies += anomalies_donnees_production()

        if anomalies:
            self.stderr.write(self.style.ERROR("Instance NON prête pour la production :"))
            for anomalie in anomalies:
                self.stderr.write(f" - {anomalie}")
            raise CommandError(f"{len(anomalies)} anomalie(s) de configuration production.")

        self.stdout.write(self.style.SUCCESS("Configuration production : OK"))
