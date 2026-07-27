from django.apps import AppConfig


class ElearningConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.elearning"
    verbose_name = "E-Learning"

    def ready(self):
        from apps.elearning import (
            checks,  # noqa: F401 — contrôles de configuration
            signals,  # noqa: F401 — enregistrement du récepteur
        )
