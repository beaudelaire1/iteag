"""
Management command: create Wagtail Site + HomePage + child pages so the public site renders.
Usage: python manage.py setup_initial_pages
"""

from django.core.management.base import BaseCommand

from wagtail.models import Page, Site

from apps.website.models import (
    HomePage,
    ContentPage,
    NewsIndexPage,
    EventIndexPage,
    FAQPage,
    ContactPage,
)


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
        Page.objects.filter(depth=2, slug="home").exclude(
            content_type__model="homepage"
        ).delete()

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
        self._create_child_page(home, ContentPage, "Découvrir l'ITEAG", "presentation")
        self._create_child_page(home, NewsIndexPage, "Actualités", "actualites",
                                introduction="<p>Retrouvez toutes les actualités de l'ITEAG.</p>")
        self._create_child_page(home, EventIndexPage, "Événements", "evenements",
                                introduction="<p>Les prochains événements de l'ITEAG.</p>")
        self._create_child_page(home, FAQPage, "Questions fréquentes", "faq")
        self._create_child_page(home, ContactPage, "Contact", "contact",
                                introduction="<p>Vous avez une question ? Contactez-nous.</p>",
                                thank_you_text="<p>Merci pour votre message. Nous reviendrons vers vous rapidement.</p>")

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
