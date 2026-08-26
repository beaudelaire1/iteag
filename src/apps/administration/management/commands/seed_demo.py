"""
Peuple l'ensemble de la plateforme pour une démonstration.

Usage : python manage.py seed_demo

Une seule commande à lancer avant une présentation. Elle enchaîne les jeux de
données de chaque application, dans l'ordre où ils dépendent les uns des
autres — le référentiel des formations d'abord, puisque tout s'y rattache.

L'orchestration passe par `call_command`, qui prend un **nom**, pas un import :
cette application n'acquiert donc aucune dépendance métier supplémentaire et
l'invariant d'architecture reste vérifié.

Chaque sous-commande est idempotente : relancer `seed_demo` complète le jeu
sans le dupliquer. C'est ce qui permet de la relancer sereinement cinq minutes
avant une démonstration.
"""

from django.core.management import call_command
from django.core.management.base import BaseCommand

# (commande, description affichée)
ETAPES = [
    ("seed_formations", "Référentiel : disciplines, parcours, professeurs, tarifs, cours"),
    ("seed_profs_detail", "Fiches détaillées des professeurs"),
    ("seed_comptes", "Comptes de connexion : secrétariat, direction, enseignants"),
    ("seed_candidatures", "Dossiers de candidature à l'admission"),
    ("seed_bibliotheque", "Catalogue de la bibliothèque"),
    ("seed_vie_academique", "Étudiants, sessions, inscriptions, paiements, stages, VAE, ECTS"),
    ("seed_lms", "Ressources, évaluations et annonces de cours"),
    ("seed_elearning_demo", "Accès aux modules vidéo et progressions"),
]


class Command(BaseCommand):
    help = "Peuple toute la plateforme avec un jeu de démonstration cohérent."

    def add_arguments(self, analyseur):
        analyseur.add_argument(
            "--sans-referentiel",
            action="store_true",
            help="Ne rejoue pas seed_formations ni seed_profs_detail (déjà en place).",
        )

    def handle(self, *args, **options):
        etapes = ETAPES
        if options["sans_referentiel"]:
            etapes = [e for e in ETAPES if not e[0].startswith(("seed_formations", "seed_profs"))]

        echecs = []
        for commande, description in etapes:
            # Sortie volontairement en ASCII : la console Windows par défaut est
            # en cp1252 et casse sur un caractère hors de cette table.
            self.stdout.write(self.style.MIGRATE_HEADING(f"\n>> {description}"))
            try:
                call_command(commande, verbosity=options.get("verbosity", 1))
            except Exception as erreur:  # noqa: BLE001 — on veut poursuivre et tout rapporter
                echecs.append((commande, erreur))
                self.stdout.write(self.style.ERROR(f"  Échec de « {commande} » : {erreur}"))

        self.stdout.write(self.style.MIGRATE_HEADING("\nRésultat"))
        if echecs:
            # Ne pas conclure au succès quand une étape a échoué : découvrir le
            # trou pendant la présentation coûte plus cher que de le lire ici.
            for commande, erreur in echecs:
                self.stdout.write(self.style.ERROR(f"  ECHEC {commande} — {erreur}"))
            self.stdout.write(self.style.ERROR(f"\n  {len(echecs)} étape(s) en échec sur {len(etapes)}."))
            return

        self.stdout.write(self.style.SUCCESS(f"  {len(etapes)} étape(s) exécutée(s). La plateforme est peuplée."))
        self.stdout.write(
            "\n  Comptes de démonstration :\n"
            "    secrétariat  secretariat_iteag  (mot de passe défini à la création)\n"
            "    étudiants    josiane.marceline, emmanuel.sainterose, …  mot de passe : DemoIteag!2026\n"
        )
