from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django_otp.plugins.otp_static.models import StaticDevice
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.accounts.models import User


class Command(BaseCommand):
    help = "Réinitialise le second facteur d'un compte sans modifier son mot de passe."

    def add_arguments(self, parser):
        parser.add_argument(
            "identifiant",
            help="Nom d'utilisateur ou adresse e-mail du compte à réinitialiser.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        identifiant = options["identifiant"].strip()
        utilisateur = (
            User.objects.filter(username__iexact=identifiant).first()
            or User.objects.filter(email__iexact=identifiant).first()
        )

        if utilisateur is None:
            raise CommandError(f"Aucun compte trouvé pour « {identifiant} ».")

        nb_totp, _ = TOTPDevice.objects.filter(user=utilisateur).delete()
        nb_static, _ = StaticDevice.objects.filter(user=utilisateur).delete()

        self.stdout.write(
            self.style.SUCCESS(
                f"2FA réinitialisée pour {utilisateur.username} "
                f"({nb_totp} appareil(s) TOTP, {nb_static} appareil(s) de secours supprimé(s))."
            )
        )
        self.stdout.write(
            "Le mot de passe n'a pas été modifié. À la prochaine connexion, "
            "le compte devra enrôler un nouvel appareil 2FA."
        )
