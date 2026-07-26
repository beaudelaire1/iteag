from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.core"
    verbose_name = "Core"

    def ready(self):
        # Contrôles de démarrage : une feuille de style absente ou périmée
        # casse la mise en page sans lever la moindre erreur.
        from apps.core import checks  # noqa: F401
