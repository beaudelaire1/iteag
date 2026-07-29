"""Envoie un jeu de contrôle couvrant les familles de courriels du site."""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email
from django.template.loader import render_to_string

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
                "1/6 — Inscription à la newsletter",
                "core/emails/newsletter_confirmation.html",
                {
                    "email": destinataire,
                    "lien_confirmation": f"{site_url}/test/confirmation-newsletter/",
                },
            ),
            (
                "2/6 — Confirmation de commande",
                "commerce/emails/confirmation_commande.html",
                {
                    "numero": "TEST-0001",
                    "nom": "Destinataire test",
                    "total": "49.80",
                    "mode_paiement": "Carte bancaire",
                    "suivi_url": f"{site_url}/test/suivi-commande/",
                },
            ),
            (
                "3/6 — Changement de statut d'une commande",
                "commerce/emails/statut_commande.html",
                {
                    "numero": "TEST-0001",
                    "nom": "Destinataire test",
                    "statut": "Expédiée",
                    "message": "Votre commande a quitté nos locaux.",
                    "transporteur": "La Poste",
                    "numero_suivi": "TEST-SUIVI",
                    "url_suivi_transporteur": "https://www.laposte.fr/outils/suivre-vos-envois",
                    "suivi_url": f"{site_url}/test/suivi-commande/",
                },
            ),
            (
                "4/6 — Alerte de stock",
                "commerce/emails/alerte_stock.html",
                {
                    "titre": "Livre de test",
                    "sku": "TEST-001",
                    "stock_disponible": 2,
                    "seuil": 3,
                },
            ),
            (
                "5/6 — Bienvenue étudiant",
                "administration/emails/bienvenue_etudiant.html",
                {
                    "prenom": "Étudiant test",
                    "parcours": "Parcours de test",
                    "lien_activation": f"{site_url}/test/activation/",
                },
            ),
        ]

        for sujet, gabarit, contexte in controles_html:
            if not envoyer_maintenant(sujet, gabarit, contexte, [destinataire]):
                raise CommandError(f"Échec du contrôle « {sujet} ».")
            self.stdout.write(self.style.SUCCESS(f"OK — {sujet}"))

        corps = render_to_string(
            "accounts/password_reset_email.txt",
            {
                "protocol": "https",
                "domain": "iteag.org",
                "uid": "test",
                "token": "test-notification",
            },
        )
        nombre = send_mail(
            subject="[ITEAG] 6/6 — Notifications texte et mot de passe",
            message=corps,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[destinataire],
            fail_silently=False,
        )
        if nombre != 1:
            raise CommandError("Le contrôle des notifications texte n'a pas été envoyé.")

        self.stdout.write(self.style.SUCCESS("OK — 6/6 — Notifications texte et mot de passe"))
        self.stdout.write(self.style.SUCCESS(f"6 notifications de contrôle envoyées à {destinataire}."))

    def _verifier_configuration(self, destinataire):
        if not destinataire:
            raise CommandError("Renseignez EMAIL_TEST_RECIPIENT ou utilisez --destinataire.")
        try:
            validate_email(destinataire)
        except ValidationError as erreur:
            raise CommandError("EMAIL_TEST_RECIPIENT n'est pas une adresse valide.") from erreur

        if settings.EMAIL_BACKEND != "django.core.mail.backends.smtp.EmailBackend":
            raise CommandError("Le backend SMTP n'est pas actif. Vérifiez EMAIL_HOST_USER et EMAIL_HOST_PASSWORD.")

        manquantes = [
            nom for nom in ("EMAIL_HOST", "EMAIL_HOST_USER", "EMAIL_HOST_PASSWORD") if not getattr(settings, nom, "")
        ]
        if manquantes:
            raise CommandError(f"Configuration SMTP incomplète : {', '.join(manquantes)}.")
