from django.core.management.base import BaseCommand, CommandError

from apps.core.services.production import anomalies_configuration_production


class Command(BaseCommand):
    help = "Vérifie que l'instance est configurée pour une ouverture publique en production."

    def handle(self, *args, **options):
        anomalies = anomalies_configuration_production()
        if anomalies:
            self.stderr.write(self.style.ERROR("Instance NON prête pour la production :"))
            for anomalie in anomalies:
                self.stderr.write(f" - {anomalie}")
            raise CommandError(f"{len(anomalies)} anomalie(s) de configuration production.")

        self.stdout.write(self.style.SUCCESS("Configuration production : OK"))
