"""
Peuple l'e-learning : accès aux modules et progressions.

Usage : python manage.py seed_elearning_demo

Le tableau de bord du secrétariat, l'écran d'audience de l'enseignant et les
statistiques d'accès lisent tous ces données. Sans inscriptions ni
progressions, ils affichent des zéros — et un graphique à zéro ne montre pas
qu'il sait tracer une courbe.

Les accès couvrent les états que le secrétariat sait administrer : actif,
demande en attente, suspendu, terminé, révoqué. C'est précisément la liste
d'écrans « Accès aux modules » qui s'en trouve démontrable.
"""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.academics.models import ProfilEtudiant
from apps.elearning.models import InscriptionModule, ModuleFormation, ProgressionLecon

ETATS = [
    (InscriptionModule.StatutAcces.ACTIF, 65),
    (InscriptionModule.StatutAcces.ACTIF, 30),
    (InscriptionModule.StatutAcces.TERMINE, 100),
    (InscriptionModule.StatutAcces.DEMANDE, 0),
    (InscriptionModule.StatutAcces.ACTIF, 10),
    (InscriptionModule.StatutAcces.SUSPENDU, 45),
    (InscriptionModule.StatutAcces.ACTIF, 85),
    (InscriptionModule.StatutAcces.REVOQUE, 20),
]


class Command(BaseCommand):
    help = "Insère des accès aux modules e-learning et des progressions de lecture."

    @transaction.atomic
    def handle(self, *args, **options):
        modules = list(ModuleFormation.objects.all())
        etudiants = list(ProfilEtudiant.objects.select_related("utilisateur").order_by("numero_etudiant"))
        if not modules or not etudiants:
            self.stdout.write(
                self.style.ERROR(
                    "Modules ou étudiants absents — lancez « seed_formations » puis « seed_vie_academique »."
                )
            )
            return

        maintenant = timezone.now()
        for index, etudiant in enumerate(etudiants):
            module = modules[index % len(modules)]
            statut, avancement = ETATS[index % len(ETATS)]

            inscription, _ = InscriptionModule.objects.get_or_create(
                etudiant=etudiant,
                module=module,
                defaults={
                    "source": InscriptionModule.SourceAcces.PARCOURS
                    if index % 3
                    else InscriptionModule.SourceAcces.OCTROI_MANUEL,
                    "statut": statut,
                    "progression_percent": avancement,
                    "date_debut_acces": timezone.localdate() - timedelta(days=30 + index),
                    "motif_revocation": (
                        "Accès retiré à la demande du secrétariat."
                        if statut == InscriptionModule.StatutAcces.REVOQUE
                        else ""
                    ),
                    "date_completion": maintenant if statut == InscriptionModule.StatutAcces.TERMINE else None,
                },
            )

            if inscription.statut == InscriptionModule.StatutAcces.DEMANDE:
                continue

            # Progression leçon par leçon, cohérente avec le pourcentage global :
            # un module à 65 % dont aucune leçon n'est vue se verrait au premier
            # clic sur le détail.
            lecons = list(module.lecons())
            if not lecons:
                continue
            faites = round(len(lecons) * inscription.progression_percent / 100)
            for rang, lecon in enumerate(lecons):
                terminee = rang < faites
                ProgressionLecon.objects.get_or_create(
                    inscription=inscription,
                    lecon=lecon,
                    defaults={
                        "position_secondes": lecon.duree_secondes if terminee else lecon.duree_secondes // 3,
                        "pourcentage_vu": 100 if terminee else 35,
                        "temps_visionnage_cumule": lecon.duree_secondes if terminee else lecon.duree_secondes // 3,
                        "termine": terminee,
                        "date_completion": maintenant if terminee else None,
                    },
                )

        self.stdout.write(
            self.style.SUCCESS(
                f"E-learning : {InscriptionModule.objects.count()} accès, "
                f"{ProgressionLecon.objects.count()} progression(s) de leçon."
            )
        )
