from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.accounts"
    verbose_name = "Comptes utilisateurs"

    def ready(self):
        # Importé ici : au moment de l'import du module, les modèles ne sont pas
        # encore prêts et le branchement échouerait.
        from apps.accounts import signaux  # noqa: F401
