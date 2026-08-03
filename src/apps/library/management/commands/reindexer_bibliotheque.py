"""Recalcule le vecteur de recherche de toutes les notices.

Le vecteur n'est produit qu'au `save()` d'une instance. Tout ce qui écrit en
masse — import, chargement de données, migration — laisse donc des notices
avec un vecteur nul, invisibles à la recherche plein texte sans qu'aucune
erreur ne le signale. À passer après chaque import, et après toute évolution
des champs indexés.
"""

from django.core.management.base import BaseCommand
from django.db import connection

from apps.library.models import NoticeBibliographique


class Command(BaseCommand):
    help = "Recalcule le vecteur de recherche des notices bibliographiques."

    def handle(self, *args, **options):
        if connection.vendor != "postgresql":
            self.stdout.write(self.style.WARNING("Recherche plein texte indisponible hors PostgreSQL : rien à faire."))
            return

        total = NoticeBibliographique.objects.update(search_vector=NoticeBibliographique.vecteur_de_recherche())
        restantes = NoticeBibliographique.objects.filter(search_vector__isnull=True).count()

        self.stdout.write(self.style.SUCCESS(f"{total} notice(s) réindexée(s)."))
        if restantes:
            self.stdout.write(self.style.ERROR(f"{restantes} notice(s) restent sans vecteur."))
