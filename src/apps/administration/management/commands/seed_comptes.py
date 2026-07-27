"""
Crée les comptes de connexion : secrétariat, direction, et un par professeur.

Usage :
    python manage.py seed_comptes
    python manage.py seed_comptes --mot-de-passe "…"

Sans compte, une fiche de professeur n'est qu'une notice publique : son
titulaire ne peut ni déposer de ressource, ni noter une copie, ni publier de
notes. Sept fiches existaient pour un seul compte — six enseignants étaient
donc invisibles de leur propre portail.

Cette application est le bon endroit pour cela : administrer les utilisateurs
est précisément ce que le portail d'administration fait.

Le mot de passe par défaut est un mot de passe de démonstration. Il n'est
acceptable que sur un poste de travail ; passez `--mot-de-passe` pour tout
environnement accessible depuis l'extérieur.
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.text import slugify

from apps.accounts.models import User
from apps.formations.models import Professeur

MOT_DE_PASSE_DEFAUT = "DemoIteag!2026"


class Command(BaseCommand):
    help = "Crée les comptes secrétariat, direction et enseignants manquants."

    def add_arguments(self, analyseur):
        analyseur.add_argument(
            "--mot-de-passe",
            dest="mot_de_passe",
            default=MOT_DE_PASSE_DEFAUT,
            help="Mot de passe appliqué aux comptes créés.",
        )
        analyseur.add_argument(
            "--reinitialiser",
            action="store_true",
            help="Réapplique le mot de passe aux comptes qui existent déjà.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        mot_de_passe = options["mot_de_passe"]
        reinitialiser = options["reinitialiser"]

        crees = []
        crees += self._compte_de_service(
            "secretariat_iteag",
            "secretariat@iteag.org",
            "Secrétariat",
            "ITEAG",
            User.Role.SECRETARIAT,
            mot_de_passe,
            reinitialiser,
        )
        crees += self._compte_de_service(
            "direction_iteag",
            "direction@iteag.org",
            "Direction",
            "ITEAG",
            User.Role.ADMIN,
            mot_de_passe,
            reinitialiser,
        )
        enseignants = self._comptes_enseignants(mot_de_passe, reinitialiser)

        self.stdout.write(
            self.style.SUCCESS(f"Comptes : {len(crees)} compte(s) de service, {enseignants} enseignant(s) rattaché(s).")
        )
        self.stdout.write(f"  Mot de passe appliqué aux comptes créés : {mot_de_passe}")

    def _compte_de_service(self, identifiant, courriel, prenom, nom, role, mot_de_passe, reinitialiser):
        utilisateur, cree = User.objects.get_or_create(
            username=identifiant,
            defaults={
                "email": courriel,
                "first_name": prenom,
                "last_name": nom,
                "role": role,
                "is_active": True,
            },
        )
        if cree or reinitialiser:
            utilisateur.set_password(mot_de_passe)
            utilisateur.role = role
            utilisateur.is_active = True
            utilisateur.save()
        return [identifiant] if cree else []

    def _comptes_enseignants(self, mot_de_passe, reinitialiser) -> int:
        """Un compte par fiche de professeur, rattaché à elle."""
        rattaches = 0
        for professeur in Professeur.objects.filter(actif=True):
            if professeur.user_id and not reinitialiser:
                continue

            base = slugify(f"{professeur.prenom}.{professeur.nom}").replace("-", ".") or f"prof{professeur.pk}"
            identifiant = base
            suffixe = 1
            while User.objects.filter(username=identifiant).exclude(pk=professeur.user_id).exists():
                suffixe += 1
                identifiant = f"{base}{suffixe}"

            if professeur.user_id:
                utilisateur = professeur.user
                utilisateur.set_password(mot_de_passe)
                utilisateur.save(update_fields=["password"])
                continue

            utilisateur = User.objects.create_user(
                username=identifiant,
                email=f"{identifiant}@iteag.org",
                password=mot_de_passe,
                first_name=professeur.prenom,
                last_name=professeur.nom,
                role=User.Role.ENSEIGNANT,
            )
            professeur.user = utilisateur
            professeur.save(update_fields=["user", "updated_at"])
            rattaches += 1
        return rattaches
