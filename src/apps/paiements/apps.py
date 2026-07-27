from django.apps import AppConfig


class PaiementsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.paiements"
    verbose_name = "Paiements en ligne"

    def ready(self):
        from apps.paiements import checks  # noqa: F401
