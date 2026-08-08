"""Éprouve le stockage média configuré par une écriture, lecture et suppression réelles."""

from __future__ import annotations

from uuid import uuid4

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandError

CONTENU = b"ITEAG go-live storage probe\n"


class Command(BaseCommand):
    help = "Vérifie le stockage média réel : écriture, lecture et suppression d'un objet de contrôle."

    def handle(self, *args, **options):
        nom = f"go-live-tests/{uuid4().hex}.txt"
        enregistre = ""
        try:
            enregistre = default_storage.save(nom, ContentFile(CONTENU))
            if not default_storage.exists(enregistre):
                raise CommandError("Le stockage n'indique pas l'objet de contrôle comme présent après écriture.")

            with default_storage.open(enregistre, "rb") as fichier:
                lu = fichier.read()
            if lu != CONTENU:
                raise CommandError("Le contenu relu diffère de celui qui a été écrit.")

            default_storage.delete(enregistre)
            if default_storage.exists(enregistre):
                raise CommandError("L'objet de contrôle existe encore après suppression.")

            self.stdout.write(self.style.SUCCESS("OK — stockage média : écriture, lecture et suppression validées."))
        except CommandError:
            raise
        except Exception as erreur:
            raise CommandError(f"Échec du contrôle du stockage média : {erreur}") from erreur
        finally:
            # Nettoyage de dernier recours si l'échec survient entre l'écriture
            # et la suppression normale. Une erreur de nettoyage ne doit pas
            # masquer la cause initiale du contrôle, mais elle doit rester visible.
            if enregistre:
                try:
                    if default_storage.exists(enregistre):
                        default_storage.delete(enregistre)
                except Exception as erreur_nettoyage:  # noqa: BLE001
                    self.stderr.write(
                        self.style.WARNING(
                            f"ATTENTION — impossible de nettoyer l'objet de contrôle {enregistre!r} : "
                            f"{erreur_nettoyage}"
                        )
                    )
