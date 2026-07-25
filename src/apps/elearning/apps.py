from django.apps import AppConfig


class ElearningConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.elearning"
    verbose_name = "Formation vidéo"

    def ready(self):
        from apps.elearning import signals  # noqa: F401 — enregistrement du récepteur
