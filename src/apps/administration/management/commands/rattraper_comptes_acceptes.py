"""
Rejoue la création de compte des dossiers acceptés restés sans compte.

L'acceptation groupée faisait passer un dossier à « accepté » sans créer le
compte étudiant. « Accepté » étant terminal, la fiche ne permettait plus de
rattraper : le candidat restait accepté et sans espace. La commande existe pour
réparer ces dossiers sans passer par un shell de production, où une faute de
frappe se paie comptant.

Elle est idempotente : un dossier réparé n'est plus retenu au passage suivant.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.administration.services.admission import accepter_dossier, promotion_par_defaut
from apps.admissions.models import DossierCandidature


class Command(BaseCommand):
    help = "Recrée les comptes des candidatures acceptées restées sans utilisateur."

    def add_arguments(self, parser):
        parser.add_argument(
            "--simuler",
            action="store_true",
            help="Énumère les dossiers concernés sans rien créer.",
        )

    def handle(self, *args, **options):
        simuler = options["simuler"]
        dossiers = DossierCandidature.objects.filter(
            statut=DossierCandidature.Statut.ACCEPTE,
            utilisateur_cree__isnull=True,
        ).select_related("parcours_souhaite")

        if not dossiers.exists():
            self.stdout.write(self.style.SUCCESS("Aucun dossier accepté sans compte : rien à rattraper."))
            return

        repares, ignores = 0, 0
        for dossier in dossiers:
            promotion = promotion_par_defaut(dossier)
            if promotion is None:
                ignores += 1
                self.stderr.write(
                    self.style.WARNING(
                        f"{dossier.nom_complet} : aucune promotion active pour « {dossier.parcours_souhaite} ». "
                        "Ouvrez-en une, puis relancez."
                    )
                )
                continue

            if simuler:
                self.stdout.write(f"À rattraper : {dossier.nom_complet} → {promotion.nom}")
                repares += 1
                continue

            try:
                # Un dossier par transaction : l'échec de l'un ne doit pas
                # défaire les comptes déjà créés pour les autres.
                with transaction.atomic():
                    profil = accepter_dossier(dossier, promotion=promotion)
            except Exception as erreur:  # noqa: BLE001 — le détail est rapporté et le passage continue
                ignores += 1
                self.stderr.write(self.style.ERROR(f"{dossier.nom_complet} : {erreur}"))
            else:
                repares += 1
                self.stdout.write(f"{dossier.nom_complet} → compte {profil.numero_etudiant} créé.")

        verbe = "à rattraper" if simuler else "rattrapé(s)"
        self.stdout.write(self.style.SUCCESS(f"{repares} dossier(s) {verbe}, {ignores} en échec."))
