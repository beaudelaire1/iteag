"""Envoie un jeu de contrôle couvrant les familles de courriels du site."""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email

from apps.core.services.emails import envoyer_maintenant


class Command(BaseCommand):
    help = "Envoie les notifications de contrôle à une adresse sans modifier les données du site."

    def add_arguments(self, parser):
        parser.add_argument(
            "--destinataire",
            default="",
            help="Adresse de réception. Par défaut, utilise EMAIL_TEST_RECIPIENT.",
        )

    def handle(self, *args, **options):
        destinataire = (options["destinataire"] or settings.EMAIL_TEST_RECIPIENT).strip()
        self._verifier_configuration(destinataire)

        site_url = settings.SITE_URL.rstrip("/")
        controles_html = [
            (
                "1/4 — Notification d'une action sur le site",
                "core/emails/notification.html",
                {
                    "titre": "Une action requiert votre attention",
                    "message": (
                        "Ce gabarit est utilisé pour les cours, devoirs, candidatures, "
                        "inscriptions, documents et décisions administratives."
                    ),
                    "lien": f"{site_url}/",
                    "libelle_lien": "Ouvrir mon espace",
                },
            ),
            (
                "2/4 — Inscription à la newsletter",
                "core/emails/newsletter_confirmation.html",
                {
                    "email": destinataire,
                    "lien_confirmation": f"{site_url}/test/confirmation-newsletter/",
                },
            ),
            (
                "3/4 — Bienvenue étudiant",
                "administration/emails/bienvenue_etudiant.html",
                {
                    "prenom": "Étudiant test",
                    "parcours": "Parcours de test",
                    "lien_activation": f"{site_url}/test/activation/",
                },
            ),
            (
                "4/4 — Réinitialisation du mot de passe",
                "accounts/password_reset_email.html",
                {
                    "protocol": "https",
                    "domain": "iteag.org",
                    "uid": "test",
                    "token": "test-notification",
                },
            ),
        ]

        for sujet, gabarit, contexte in controles_html:
            if not envoyer_maintenant(sujet, gabarit, contexte, [destinataire]):
                raise CommandError(f"Échec du contrôle « {sujet} ».")
            self.stdout.write(self.style.SUCCESS(f"OK — {sujet}"))

        self.stdout.write(self.style.SUCCESS(f"4 notifications de contrôle envoyées à {destinataire}."))

    def _verifier_configuration(self, destinataire):
        if not destinataire:
            raise CommandError("Renseignez EMAIL_TEST_RECIPIENT ou utilisez --destinataire.")
        try:
            validate_email(destinataire)
        except ValidationError as erreur:
            raise CommandError("EMAIL_TEST_RECIPIENT n'est pas une adresse valide.") from erreur

        if settings.EMAIL_BACKEND != "django.core.mail.backends.smtp.EmailBackend":
            raise CommandError("Le backend SMTP n'est pas actif. Vérifiez les paramètres EMAIL_HOST.")

        manquantes = [
            nom for nom in ("EMAIL_HOST", "EMAIL_HOST_USER", "EMAIL_HOST_PASSWORD") if not getattr(settings, nom, "")
        ]
        if manquantes:
            raise CommandError(f"Configuration SMTP incomplète : {', '.join(manquantes)}.")
