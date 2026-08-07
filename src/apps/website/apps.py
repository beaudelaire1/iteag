from django.apps import AppConfig


class WebsiteConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.website"
    verbose_name = "Site public"

    def ready(self):
        # Le gabarit historique reste intact. Cette enveloppe ajoute seulement
        # les témoignages étudiants validés, sans dupliquer les centaines de
        # lignes de l'accueil ni casser les témoignages éditoriaux existants.
        from apps.website.models import HomePage

        HomePage.template = "website/home_page_temoignages.html"
