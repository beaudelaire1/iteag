"""
Management command: create Wagtail Site + HomePage + child pages so the public site renders.
Usage: python manage.py setup_initial_pages
"""

from django.core.management.base import BaseCommand
from wagtail.models import Page, Site

from apps.website.models import (
    ContactPage,
    ContentPage,
    EventIndexPage,
    FAQPage,
    HomePage,
    NewsIndexPage,
)


PRESENTATION_META = (
    "Découvrir l'ITEAG, centre de formation en théologie évangélique des Antilles et de la Guyane : "
    "sa vocation, sa forme associative et les principes de sa formation."
)


def contenu_presentation_initial():
    """Contenu institutionnel repris de la présentation officielle iteag.org.

    Les formulations sont volontairement sobres : aucun chiffre, partenariat,
    accréditation ou élément historique n'est ajouté sans source institutionnelle.
    Les identifiants fixes rendent le contenu StreamField stable d'une installation
    à l'autre et simplifient les tests.
    """
    return [
        {
            "type": "texte",
            "id": "593cb50e-ffb2-4e89-aa90-2b6949a11cef",
            "value": (
                "<p>L'Institut de Théologie Évangélique des Antilles et de la Guyane est un centre de formation "
                "en théologie évangélique. Il s'adresse à celles et ceux qui souhaitent librement développer "
                "leurs connaissances théologiques ou suivre un parcours diplômant afin de mieux exercer un "
                "ministère au sein de leur assemblée.</p>"
            ),
        },
        {
            "type": "texte",
            "id": "b7887e9a-af61-45ad-b7c0-741a2c1cab79",
            "value": (
                "<h2>L'ITEAG, qu'est-ce que c'est ?</h2>"
                "<p>La vocation de l'ITEAG est la formation théologique. L'institut articule l'acquisition de "
                "connaissances et la préparation au service dans les Églises, avec la possibilité de se former "
                "par intérêt personnel ou dans le cadre d'un parcours conduisant à un diplôme.</p>"
            ),
        },
        {
            "type": "encadre",
            "id": "4277360f-af3a-4699-8e47-d5b97da4eb07",
            "value": {
                "titre": "Un projet fédérateur",
                "contenu": (
                    "<p>L'ITEAG se présente comme une association loi 1905 et comme un projet fédérateur "
                    "œuvrant à l'unité évangélique.</p>"
                ),
                "tonalite": "information",
            },
        },
        {
            "type": "texte",
            "id": "bcda39ce-cea2-4995-b33e-06f730d7cf47",
            "value": (
                "<h2>Pourquoi choisir l'ITEAG ?</h2>"
                "<p>L'institut met en avant une formation de qualité au service d'une pratique efficace :</p>"
                "<ul>"
                "<li>une formation dispensée localement ;</li>"
                "<li>une équipe pédagogique engagée spirituellement et compétente académiquement ;</li>"
                "<li>une formation à la fois théorique et pratique ;</li>"
                "<li>des personnes en formation disponibles pour les Églises tout au long de leur cursus ;</li>"
                "<li>une bibliothèque accessible aux étudiants.</li>"
                "</ul>"
            ),
        },
        {
            "type": "texte",
            "id": "6ae1b0e8-ffac-46dc-8711-25134a8d1e13",
            "value": (
                "<h2>Se former à l'ITEAG</h2>"
                "<p>Les parcours proposés permettent d'aborder la formation théologique selon son projet : "
                "approfondissement personnel, préparation au ministère ou parcours diplômant.</p>"
                "<p><a href=\"/formations/\">Découvrir les formations proposées</a></p>"
            ),
        },
    ]


class Command(BaseCommand):
    help = "Create the Wagtail root page structure and default Site."

    def handle(self, *args, **options):
        # 1. Fix the Wagtail page tree and get root
        Page.fix_tree()
        root = Page.objects.filter(depth=1).first()
        if root is None:
            self.stderr.write(self.style.ERROR("No Wagtail root page found. Run migrate first."))
            return

        # 2. Create (or get) our HomePage
        try:
            home = HomePage.objects.get(depth=2)
            self.stdout.write(self.style.WARNING(f"HomePage already exists: '{home.title}'"))
        except HomePage.DoesNotExist:
            home = HomePage(
                title="Institut de Théologie Évangélique des Antilles et de la Guyane",
                slug="accueil",
                sous_titre="Une formation de qualité pour un service efficace",
            )
            root.add_child(instance=home)
            home.save_revision().publish()
            self.stdout.write(self.style.SUCCESS(f"HomePage created: '{home.title}'"))

        # 3. Remove default "Welcome to Wagtail" page if present
        Page.objects.filter(depth=2, slug="home").exclude(content_type__model="homepage").delete()

        # 4. Create or update the default Site
        site, created = Site.objects.get_or_create(
            is_default_site=True,
            defaults={
                "hostname": "localhost",
                "port": 80,
                "site_name": "ITEAG",
                "root_page": home,
            },
        )
        if not created:
            site.root_page = home
            site.site_name = "ITEAG"
            site.save()
            self.stdout.write(self.style.WARNING("Default site updated to point to HomePage."))
        else:
            self.stdout.write(self.style.SUCCESS("Default site created."))

        # 5. Create child pages if they don't exist
        self._create_child_page(
            home,
            ContentPage,
            "Découvrir l'ITEAG",
            "presentation",
            body=contenu_presentation_initial(),
            meta_description=PRESENTATION_META,
            search_description=PRESENTATION_META,
        )
        self._create_child_page(
            home,
            NewsIndexPage,
            "Actualités",
            "actualites",
            introduction="<p>Retrouvez toutes les actualités de l'ITEAG.</p>",
        )
        self._create_child_page(
            home, EventIndexPage, "Événements", "evenements", introduction="<p>Les prochains événements de l'ITEAG.</p>"
        )
        self._create_child_page(home, FAQPage, "Questions fréquentes", "faq")
        self._create_child_page(
            home,
            ContactPage,
            "Contact",
            "contact",
            introduction="<p>Vous avez une question ? Contactez-nous.</p>",
            thank_you_text="<p>Merci pour votre message. Nous reviendrons vers vous rapidement.</p>",
        )

        self.stdout.write(self.style.SUCCESS("Done — visit http://localhost:8000/ to see the site."))

    def _create_child_page(self, parent, page_class, title, slug, **extra_fields):
        """Create a child page under parent if it doesn't already exist."""
        if page_class.objects.filter(slug=slug).exists():
            self.stdout.write(self.style.WARNING(f"  {page_class.__name__} '{slug}' already exists."))
            return
        page = page_class(title=title, slug=slug, **extra_fields)
        parent.add_child(instance=page)
        page.save_revision().publish()
        self.stdout.write(self.style.SUCCESS(f"  {page_class.__name__} created: '{title}' (/{slug}/)"))
