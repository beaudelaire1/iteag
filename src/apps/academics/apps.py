from django.apps import AppConfig


class AcademicsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.academics"
    verbose_name = "Vie académique"

    def ready(self):
        # Les modèles d'assiduité sont isolés pour ne pas alourdir le modèle
        # académique historique, mais doivent être enregistrés au démarrage.
        from . import models_assiduite  # noqa: F401
