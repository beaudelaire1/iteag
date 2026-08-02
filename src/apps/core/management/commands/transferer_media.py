"""Transfère les fichiers déposés vers le stockage configuré.

Le défaut qu'elle répare : en développement, les fichiers déposés — photos de
professeurs, couvertures de livres, pièces de candidature — vivent dans
« src/media/ », sur le poste. En production, le stockage par défaut est
Cloudflare R2. La base, elle, ne retient qu'un chemin relatif : après un
déploiement, chaque image pointe vers un fichier que le bucket n'a jamais reçu,
et l'écran affiche un cadre vide sans qu'aucune erreur ne soit levée.

Cette commande parcourt les champs fichier de tous les modèles, et téléverse
ceux qui manquent à destination. Elle ne fait rien par défaut : sans
« --executer », elle se contente de dire ce qu'elle ferait.

    python manage.py transferer_media                 # inventaire
    python manage.py transferer_media --executer      # transfert réel

Elle est sans risque à relancer : un fichier déjà présent à destination est
laissé tel quel, sauf « --remplacer ».
"""

from pathlib import Path

from django.apps import apps
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandError
from django.db import models


class Command(BaseCommand):
    help = "Téléverse les fichiers de MEDIA_ROOT vers le stockage configuré (R2, S3…)."

    def add_arguments(self, parseur):
        parseur.add_argument(
            "--executer",
            action="store_true",
            help="Effectue réellement le transfert. Sans ce drapeau, la commande n'écrit rien.",
        )
        parseur.add_argument(
            "--remplacer",
            action="store_true",
            help="Retéléverse même si le fichier existe déjà à destination.",
        )
        parseur.add_argument(
            "--source",
            default=None,
            help="Répertoire des fichiers locaux (défaut : MEDIA_ROOT).",
        )

    def handle(self, *args, **options):
        from django.conf import settings

        source = Path(options["source"] or settings.MEDIA_ROOT)
        if not source.is_dir():
            raise CommandError(f"Répertoire source introuvable : {source}")

        executer = options["executer"]
        remplacer = options["remplacer"]

        transferes = absents = deja_presents = 0
        octets = 0

        for champ, valeurs in self._chemins_par_champ():
            for chemin_relatif in valeurs:
                fichier_local = source / chemin_relatif
                if not fichier_local.is_file():
                    absents += 1
                    self.stderr.write(f"  manquant en local : {champ} → {chemin_relatif}")
                    continue

                if not remplacer and default_storage.exists(chemin_relatif):
                    deja_presents += 1
                    continue

                taille = fichier_local.stat().st_size
                octets += taille
                transferes += 1
                if not executer:
                    continue

                # « save » renomme si le nom est pris ; on veut au contraire
                # conserver le chemin exact que la base référence.
                if remplacer and default_storage.exists(chemin_relatif):
                    default_storage.delete(chemin_relatif)
                with fichier_local.open("rb") as flux:
                    default_storage.save(chemin_relatif, ContentFile(flux.read()))

        self._resumer(executer, transferes, deja_presents, absents, octets)

    def _chemins_par_champ(self):
        """Tous les chemins référencés par un champ fichier, modèle par modèle."""
        for modele in apps.get_models():
            champs = [
                champ
                for champ in modele._meta.get_fields()
                if isinstance(champ, models.FileField) and not champ.auto_created
            ]
            if not champs:
                continue
            for champ in champs:
                valeurs = (
                    modele._default_manager.exclude(**{champ.name: ""})
                    .exclude(**{f"{champ.name}__isnull": True})
                    .values_list(champ.name, flat=True)
                )
                etiquette = f"{modele._meta.label}.{champ.name}"
                yield etiquette, [valeur for valeur in valeurs if valeur]

    def _resumer(self, executer, transferes, deja_presents, absents, octets):
        mega = octets / (1024 * 1024)
        self.stdout.write("")
        if executer:
            self.stdout.write(self.style.SUCCESS(f"{transferes} fichier(s) transféré(s) — {mega:.1f} Mo"))
        else:
            self.stdout.write(self.style.WARNING(f"{transferes} fichier(s) à transférer — {mega:.1f} Mo"))
            self.stdout.write("Relancer avec « --executer » pour les téléverser.")
        self.stdout.write(f"{deja_presents} déjà présent(s) à destination")
        if absents:
            self.stdout.write(
                self.style.ERROR(
                    f"{absents} fichier(s) référencé(s) en base mais introuvable(s) en local : "
                    "ils resteront affichés en cadre vide."
                )
            )
