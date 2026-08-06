from django.apps import AppConfig


class PaiementsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.paiements"
    verbose_name = "Paiements en ligne"

    def ready(self):
        # Modèle séparé pour relier un règlement Stripe à une demande
        # d'inscription sans alourdir le modèle financier commun.
        from apps.paiements import models_inscriptions  # noqa: F401
        from apps.paiements import checks  # noqa: F401
