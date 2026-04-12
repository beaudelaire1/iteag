from django.db import models
from django.utils import timezone

from wagtail.admin.panels import FieldPanel, MultiFieldPanel
from wagtail.fields import RichTextField, StreamField
from wagtail.models import Page
from wagtail import blocks
from wagtail.images.blocks import ImageChooserBlock
from wagtail.contrib.forms.models import AbstractForm, AbstractFormField
from modelcluster.fields import ParentalKey


# ──────────────────────────────────────────────
# StreamField Blocks
# ──────────────────────────────────────────────

class HeroBlock(blocks.StructBlock):
    titre = blocks.CharBlock(max_length=120)
    sous_titre = blocks.CharBlock(max_length=250, required=False)
    image = ImageChooserBlock(required=False)
    cta_texte = blocks.CharBlock(max_length=50, required=False, label="Texte du bouton")
    cta_lien = blocks.URLBlock(required=False, label="Lien du bouton")

    class Meta:
        icon = "home"
        label = "Bannière héro"


class SectionTexteBlock(blocks.StructBlock):
    titre = blocks.CharBlock(max_length=120)
    contenu = blocks.RichTextBlock()
    image = ImageChooserBlock(required=False)

    class Meta:
        icon = "doc-full"
        label = "Section texte"


class TemoignageBlock(blocks.StructBlock):
    nom = blocks.CharBlock(max_length=100)
    role = blocks.CharBlock(max_length=100, required=False, label="Rôle / Promotion")
    texte = blocks.TextBlock()
    photo = ImageChooserBlock(required=False)

    class Meta:
        icon = "user"
        label = "Témoignage"


class CTABlock(blocks.StructBlock):
    titre = blocks.CharBlock(max_length=120)
    description = blocks.TextBlock(required=False)
    texte_bouton = blocks.CharBlock(max_length=50)
    lien = blocks.URLBlock()

    class Meta:
        icon = "link"
        label = "Appel à l'action"


class FAQBlock(blocks.StructBlock):
    question = blocks.CharBlock(max_length=250)
    reponse = blocks.RichTextBlock()

    class Meta:
        icon = "help"
        label = "Question / Réponse"


# ──────────────────────────────────────────────
# Page models
# ──────────────────────────────────────────────

class HomePage(Page):
    """Page d'accueil — PUB-001."""

    sous_titre = models.CharField(max_length=250, blank=True, verbose_name="Sous-titre")

    body = StreamField(
        [
            ("hero", HeroBlock()),
            ("section_texte", SectionTexteBlock()),
            ("temoignages", blocks.ListBlock(TemoignageBlock(), label="Témoignages")),
            ("cta", CTABlock()),
            ("faq", blocks.ListBlock(FAQBlock(), label="FAQ")),
        ],
        blank=True,
        use_json_field=True,
        verbose_name="Contenu de la page",
    )

    # SEO fields
    meta_description = models.CharField(max_length=300, blank=True, verbose_name="Meta description")

    content_panels = Page.content_panels + [
        FieldPanel("sous_titre"),
        FieldPanel("body"),
    ]

    promote_panels = Page.promote_panels + [
        FieldPanel("meta_description"),
    ]

    class Meta:
        verbose_name = "Page d'accueil"

    parent_page_types = ["wagtailcore.Page"]
    subpage_types = ["website.ContentPage", "website.NewsIndexPage", "website.EventIndexPage", "website.FAQPage"]

    def get_context(self, request, *args, **kwargs):
        context = super().get_context(request, *args, **kwargs)
        from apps.formations.models import Parcours, Professeur

        context["featured_parcours"] = Parcours.objects.filter(actif=True)[:4]
        context["featured_professeurs"] = Professeur.objects.filter(actif=True).prefetch_related("disciplines")[:4]
        context["latest_news"] = NewsPage.objects.live().public().order_by("-date")[:3]
        context["upcoming_events"] = EventPage.objects.live().public().filter(date_debut__gte=timezone.now()).order_by("date_debut")[:3]
        context["has_editorial_body"] = bool(self.body)
        return context


class ContentPage(Page):
    """Page de contenu générique — PUB-002 (présentation, historique, mission, valeurs, etc.)."""

    body = StreamField(
        [
            ("section_texte", SectionTexteBlock()),
            ("hero", HeroBlock()),
            ("cta", CTABlock()),
        ],
        blank=True,
        use_json_field=True,
        verbose_name="Contenu",
    )

    meta_description = models.CharField(max_length=300, blank=True, verbose_name="Meta description")

    content_panels = Page.content_panels + [
        FieldPanel("body"),
    ]

    promote_panels = Page.promote_panels + [
        FieldPanel("meta_description"),
    ]

    class Meta:
        verbose_name = "Page de contenu"
        verbose_name_plural = "Pages de contenu"

    parent_page_types = ["website.HomePage"]


class NewsIndexPage(Page):
    """Page d'index des actualités — PUB-006."""

    introduction = RichTextField(blank=True, verbose_name="Introduction")
    meta_description = models.CharField(max_length=300, blank=True)

    content_panels = Page.content_panels + [
        FieldPanel("introduction"),
    ]

    promote_panels = Page.promote_panels + [
        FieldPanel("meta_description"),
    ]

    class Meta:
        verbose_name = "Index des actualités"

    parent_page_types = ["website.HomePage"]
    subpage_types = ["website.NewsPage"]


class NewsPage(Page):
    """Article d'actualité — PUB-006."""

    date = models.DateField(verbose_name="Date de publication")
    excerpt = models.TextField(max_length=500, blank=True, verbose_name="Résumé")
    body = RichTextField(verbose_name="Contenu")
    image = models.ForeignKey(
        "wagtailimages.Image",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name="Image à la une",
    )
    meta_description = models.CharField(max_length=300, blank=True)

    content_panels = Page.content_panels + [
        FieldPanel("date"),
        FieldPanel("excerpt"),
        FieldPanel("image"),
        FieldPanel("body"),
    ]

    promote_panels = Page.promote_panels + [
        FieldPanel("meta_description"),
    ]

    class Meta:
        verbose_name = "Actualité"
        verbose_name_plural = "Actualités"
        ordering = ["-date"]

    parent_page_types = ["website.NewsIndexPage"]


class EventIndexPage(Page):
    """Page d'index des événements — PUB-007."""

    introduction = RichTextField(blank=True, verbose_name="Introduction")

    content_panels = Page.content_panels + [
        FieldPanel("introduction"),
    ]

    class Meta:
        verbose_name = "Index des événements"

    parent_page_types = ["website.HomePage"]
    subpage_types = ["website.EventPage"]


class EventPage(Page):
    """Événement — PUB-007."""

    date_debut = models.DateTimeField(verbose_name="Date de début")
    date_fin = models.DateTimeField(blank=True, null=True, verbose_name="Date de fin")
    lieu = models.CharField(max_length=250, blank=True, verbose_name="Lieu")
    description = RichTextField(verbose_name="Description")
    image = models.ForeignKey(
        "wagtailimages.Image",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    content_panels = Page.content_panels + [
        MultiFieldPanel(
            [FieldPanel("date_debut"), FieldPanel("date_fin"), FieldPanel("lieu")],
            heading="Informations",
        ),
        FieldPanel("image"),
        FieldPanel("description"),
    ]

    class Meta:
        verbose_name = "Événement"
        verbose_name_plural = "Événements"
        ordering = ["-date_debut"]

    parent_page_types = ["website.EventIndexPage"]


class FAQPage(Page):
    """Page FAQ — PUB-009."""

    introduction = RichTextField(blank=True)
    questions = StreamField(
        [("faq", FAQBlock())],
        blank=True,
        use_json_field=True,
        verbose_name="Questions / Réponses",
    )

    content_panels = Page.content_panels + [
        FieldPanel("introduction"),
        FieldPanel("questions"),
    ]

    class Meta:
        verbose_name = "Page FAQ"

    parent_page_types = ["website.HomePage"]


# ──────────────────────────────────────────────
# Contact form — PUB-010
# ──────────────────────────────────────────────

class FormField(AbstractFormField):
    page = ParentalKey("ContactPage", on_delete=models.CASCADE, related_name="form_fields")


class ContactPage(AbstractForm):
    """Page de contact avec formulaire Wagtail — PUB-010."""

    introduction = RichTextField(blank=True)
    thank_you_text = RichTextField(blank=True, verbose_name="Message de confirmation")
    meta_description = models.CharField(max_length=300, blank=True)

    content_panels = AbstractForm.content_panels + [
        FieldPanel("introduction"),
        FieldPanel("thank_you_text"),
    ]

    promote_panels = Page.promote_panels + [
        FieldPanel("meta_description"),
    ]

    class Meta:
        verbose_name = "Page de contact"

    parent_page_types = ["website.HomePage"]
