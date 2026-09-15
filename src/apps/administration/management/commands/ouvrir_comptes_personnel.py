"""
Ouvre les comptes nominatifs du personnel et referme ceux de démonstration.

Usage :
    python manage.py ouvrir_comptes_personnel

La migration accounts 0006 fait la même chose sur la base en service. La
commande sert à une installation neuve, où la migration passe avant que
l'arborescence Wagtail n'existe. Elle est idempotente : un compte déjà pris en
main par son titulaire n'est jamais réécrit.
"""

from django.core.management.base import BaseCommand

from apps.administration.services.personnel import installer_personnel_iteag


class Command(BaseCommand):
    help = "Ouvre les comptes du personnel ITEAG et referme les comptes de démonstration."

    def handle(self, *args, **options):
        bilan = installer_personnel_iteag()
        self.stdout.write(f"Comptes de démonstration refermés : {', '.join(bilan['neutralises']) or 'aucun'}")
        self.stdout.write(f"Comptes du personnel : {', '.join(bilan['ouverts']) or 'aucun'}")
        self.stdout.write(self.style.SUCCESS(f"Invitations envoyées : {', '.join(bilan['invites']) or 'aucune'}"))
