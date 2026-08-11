from django import forms as django_forms
from django.db import models
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.utils import timezone
from modelcluster.fields import ParentalKey
from wagtail import blocks
from wagtail.admin.panels import FieldPanel, MultiFieldPanel
from wagtail.contrib.forms.models import AbstractForm, AbstractFormField
from wagtail.documents.blocks import DocumentChooserBlock
from wagtail.fields import RichTextField, StreamField
from wagtail.images.blocks import ImageChooserBlock
from wagtail.models import Page

from apps.core.services.turnstile import MESSAGE_ECHEC, valider_requete

# ──────────────────────────────────────────────
# StreamField Blocks
# ──────────────────────────────────────────────

# Dans StreamField, Draftail sert au texte et non à reproduire une page entière
# dans un unique champ HTML. Les images et documents restent des blocs Wagtail :
# ils conservent ainsi leurs métadonnées, permissions et références en base.
FONCTIONNALITES_TEXTE = [
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "bold",
    "italic",
    "underline",
    "strikethrough",
    "superscript",
    "subscript",
    "code",
    "ol",
    "ul",
    "blockquote",
    "align-left",
    "align-center",
    "align-right",
    "align-justify",
    "hr",
    "link",
]


class TexteEditorialBlock(blocks.RichTextBlock):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("features", FONCTIONNALITES_TEXTE)
        kwargs.setdefault("template", "website/blocks/texte_editorial.html")
        super().__init__(*args, **kwargs)

    class Meta:
        icon = "pilcrow"
        label = "Texte riche"


class ImageEditorialeBlock(blocks.StructBlock):
    image = ImageChooserBlock()
    legende = blocks.CharBlock(required=False, max_length=250, label="Légende")
    credit = blocks.CharBlock(required=False, max_length=160, label="Crédit")
    largeur = blocks.ChoiceBlock(
        choices=[
            ("contenu", "Largeur du texte"),
            ("large", "Large"),
            ("pleine", "Pleine largeur"),
        ],
        default="contenu",
        label="Largeur",
    )

    class Meta:
        icon = "image"
        label = "Image légendée"
        template = "website/blocks/image_editoriale.html"


class CitationEditorialeBlock(blocks.StructBlock):
    citation = blocks.TextBlock(label="Citation")
    auteur = blocks.CharBlock(required=False, max_length=160, label="Auteur")
    source = blocks.CharBlock(required=False, max_length=200, label="Source")

    class Meta:
        icon = "openquote"
        label = "Citation mise en avant"
        template = "website/blocks/citation_editoriale.html"


class EncadreEditorialBlock(blocks.StructBlock):
    titre = blocks.CharBlock(required=False, max_length=140, label="Titre")
    contenu = TexteEditorialBlock(features=["bold", "italic", "underline", "ol", "ul", "link"])
    tonalite = blocks.ChoiceBlock(
        choices=[
            ("information", "Information"),
            ("important", "Important"),
            ("conseil", "Conseil"),
        ],
        default="information",
        label="Présentation",
    )

    class Meta:
        icon = "info-circle"
        label = "Encadré"
        template = "website/blocks/encadre_editorial.html"


class DocumentEditorialBlock(blocks.StructBlock):
    document = DocumentChooserBlock()
    titre = blocks.CharBlock(required=False, max_length=180, label="Libellé du lien")
    description = blocks.CharBlock(required=False, max_length=280, label="Description")

    class Meta:
        icon = "doc-full-inverse"
        label = "Document à télécharger"
        template = "website/blocks/document_editorial.html"


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
    contenu = TexteEditorialBlock()
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
    reponse = TexteEditorialBlock(features=["bold", "italic", "underline", "ol", "ul", "link"])

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
            ("texte", TexteEditorialBlock()),
            ("image", ImageEditorialeBlock()),
            ("citation", CitationEditorialeBlock()),
            ("encadre", EncadreEditorialBlock()),
            ("document", DocumentEditorialBlock()),
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

    # Affiché sous le nom du type dans « Ajouter une page ». Sans lui,
    # le rédacteur choisit entre neuf noms sans savoir lequel fait quoi.
    page_description = "La page d'accueil du site. Il n'y en a qu'une."

    class Meta:
        verbose_name = "Page d'accueil"

    parent_page_types = ["wagtailcore.Page"]
    # Wagtail exige l'accord des deux côtés : un type absent d'ici ne peut être
    # créé nulle part, quoi qu'en dise son propre « parent_page_types ». La page
    # de contact et celle du catalogue étaient dans ce cas — elles n'existaient
    # que parce qu'une commande de peuplement les avait écrites directement en
    # base, et le secrétariat ne pouvait ni en créer ni en recréer.
    subpage_types = [
        "website.ContentPage",
        "website.NewsIndexPage",
        "website.EventIndexPage",
        "website.FAQPage",
        "website.ContactPage",
        "website.ModuleCataloguePage",
    ]

    def get_context(self, request, *args, **kwargs):
        context = super().get_context(request, *args, **kwargs)
        from apps.formations.models import Parcours, Professeur

        context["featured_parcours"] = Parcours.objects.filter(actif=True)[:4]
        # La sélection d'accueil montre des visages : à ordre égal, les fiches
        # illustrées passent devant, faute de quoi la section pouvait n'afficher
        # que des initiales alors que des photos existaient plus loin.
        from django.db.models import Case, IntegerField, Value, When

        context["featured_professeurs"] = (
            Professeur.objects.filter(actif=True)
            .annotate(
                sans_photo=Case(When(photo="", then=Value(1)), default=Value(0), output_field=IntegerField()),
            )
            .prefetch_related("disciplines")
            .order_by("sans_photo", "ordre", "nom")[:4]
        )
        context["latest_news"] = NewsPage.objects.live().public().order_by("-date")[:3]
        context["upcoming_events"] = (
            EventPage.objects.live().public().filter(date_debut__gte=timezone.now()).order_by("date_debut")[:3]
        )
        context["has_editorial_body"] = bool(self.body)
        return context


class ContentPage(Page):
    """Page de contenu générique — PUB-002 (présentation, historique, mission, valeurs, etc.)."""

    body = StreamField(
        [
            ("section_texte", SectionTexteBlock()),
            ("texte", TexteEditorialBlock()),
            ("image", ImageEditorialeBlock()),
            ("citation", CitationEditorialeBlock()),
            ("encadre", EncadreEditorialBlock()),
            ("document", DocumentEditorialBlock()),
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

    # Affiché sous le nom du type dans « Ajouter une page ». Sans lui,
    # le rédacteur choisit entre neuf noms sans savoir lequel fait quoi.
    page_description = (
        "Page éditoriale libre — présentation, historique, mentions légales. Peut contenir des sous-pages."
    )

    class Meta:
        verbose_name = "Page de contenu"
        verbose_name_plural = "Pages de contenu"

    parent_page_types = ["website.HomePage", "website.ContentPage"]
    # Une rubrique éditoriale se compose de sous-pages — « L'institut » et ses
    # chapitres, par exemple. Sans cela le site reste plat, et les douze pages
    # à reprendre de l'ancien site s'alignent toutes à la racine.
    subpage_types = ["website.ContentPage"]


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

    # Affiché sous le nom du type dans « Ajouter une page ». Sans lui,
    # le rédacteur choisit entre neuf noms sans savoir lequel fait quoi.
    page_description = "La liste des actualités. Les actualités se créent à l'intérieur."

    class Meta:
        verbose_name = "Index des actualités"

    parent_page_types = ["website.HomePage"]
    subpage_types = ["website.NewsPage"]

    def get_context(self, request, *args, **kwargs):
        context = super().get_context(request, *args, **kwargs)
        articles = NewsPage.objects.child_of(self).live().public().order_by("-date")
        context["articles"] = articles
        return context


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

    # Affiché sous le nom du type dans « Ajouter une page ». Sans lui,
    # le rédacteur choisit entre neuf noms sans savoir lequel fait quoi.
    page_description = "Une actualité datée, avec image à la une."

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

    # Affiché sous le nom du type dans « Ajouter une page ». Sans lui,
    # le rédacteur choisit entre neuf noms sans savoir lequel fait quoi.
    page_description = "La liste des événements. Les événements se créent à l'intérieur."

    class Meta:
        verbose_name = "Index des événements"

    parent_page_types = ["website.HomePage"]
    subpage_types = ["website.EventPage"]

    def get_context(self, request, *args, **kwargs):
        context = super().get_context(request, *args, **kwargs)
        events = EventPage.objects.child_of(self).live().public().order_by("-date_debut")
        context["events"] = events
        return context


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

    # Affiché sous le nom du type dans « Ajouter une page ». Sans lui,
    # le rédacteur choisit entre neuf noms sans savoir lequel fait quoi.
    page_description = "Un événement daté et localisé."

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

    # Affiché sous le nom du type dans « Ajouter une page ». Sans lui,
    # le rédacteur choisit entre neuf noms sans savoir lequel fait quoi.
    page_description = "Questions fréquentes, présentées en accordéons."

    class Meta:
        verbose_name = "Page FAQ"

    parent_page_types = ["website.HomePage"]


# ──────────────────────────────────────────────
# Catalogue E-Learning — page éditoriale
# ──────────────────────────────────────────────


class ModuleCataloguePage(Page):
    """
    Introduction rédigée du catalogue vidéo.

    Le secrétariat écrit l'accroche et les arguments sans développeur ; la liste
    des modules, elle, reste dynamique et suit les publications des enseignants.
    """

    accroche = models.CharField(
        max_length=250,
        blank=True,
        help_text="Phrase d'accroche affichée sous le titre.",
    )
    introduction = RichTextField(blank=True)
    arguments = StreamField(
        [("argument", SectionTexteBlock())],
        blank=True,
        use_json_field=True,
        verbose_name="Arguments",
        help_text="Ce qui distingue la formation à distance de l'ITEAG.",
    )
    texte_appel = models.CharField(
        max_length=120,
        blank=True,
        default="Déposer une candidature",
        verbose_name="Texte du bouton d'appel",
    )

    content_panels = Page.content_panels + [
        FieldPanel("accroche"),
        FieldPanel("introduction"),
        FieldPanel("arguments"),
        FieldPanel("texte_appel"),
    ]

    # Affiché sous le nom du type dans « Ajouter une page ». Sans lui,
    # le rédacteur choisit entre neuf noms sans savoir lequel fait quoi.
    page_description = "L'introduction éditoriale au catalogue des modules vidéo."

    class Meta:
        verbose_name = "Page catalogue E-Learning"

    parent_page_types = ["website.HomePage"]

    def get_context(self, request, *args, **kwargs):
        from apps.elearning.models import ModuleFormation

        contexte = super().get_context(request, *args, **kwargs)
        contexte["modules"] = (
            ModuleFormation.objects.filter(statut=ModuleFormation.StatutPublication.PUBLIE)
            .select_related("discipline", "responsable")
            .order_by("ordre", "titre")
        )
        return contexte


# ──────────────────────────────────────────────
# Contact form — PUB-010
# ──────────────────────────────────────────────


class FormField(AbstractFormField):
    page = ParentalKey("ContactPage", on_delete=models.CASCADE, related_name="form_fields")


class ContactPage(AbstractForm):
    """Page de contact avec formulaire Wagtail — PUB-010."""

    # Wagtail déduit sinon « website/contact_page_landing.html ». La page de
    # confirmation existe déjà sous ce nom et sert aussi à son URL dédiée.
    landing_page_template = "website/contact_success.html"

    introduction = RichTextField(blank=True)
    thank_you_text = RichTextField(blank=True, verbose_name="Message de confirmation")
    meta_description = models.CharField(max_length=300, blank=True)
    destinataire = models.EmailField(
        default="secretariat@iteag.org",
        verbose_name="Email destinataire",
        help_text="Adresse qui recevra les messages du formulaire.",
    )

    content_panels = AbstractForm.content_panels + [
        FieldPanel("introduction"),
        FieldPanel("thank_you_text"),
        FieldPanel("destinataire"),
    ]

    promote_panels = Page.promote_panels + [
        FieldPanel("meta_description"),
    ]

    # Affiché sous le nom du type dans « Ajouter une page ». Sans lui,
    # le rédacteur choisit entre neuf noms sans savoir lequel fait quoi.
    page_description = "Le formulaire de contact et les coordonnées de l'institut."

    class Meta:
        verbose_name = "Page de contact"

    parent_page_types = ["website.HomePage"]

    def serve(self, request, *args, **kwargs):
        """Traite le formulaire seulement après validation du défi Turnstile."""
        if request.method == "POST":
            form = self.get_form(request.POST, request.FILES, page=self, user=request.user)
            if form.is_valid():
                if valider_requete(request, action="contact"):
                    self.process_form_submission(form)
                    # Post/Redirect/Get : actualiser la confirmation ne doit
                    # ni recréer la soumission, ni renvoyer les deux emails.
                    return redirect("website:contact_success")
                form.add_error(None, MESSAGE_ECHEC)
        else:
            form = self.get_form(page=self, user=request.user)

        contexte = self.get_context(request)
        contexte["form"] = form
        return TemplateResponse(request, self.get_template(request), contexte)

    def process_form_submission(self, form):
        # Honeypot anti-spam : si le champ caché est rempli, on ignore la soumission
        if form.data.get("honeypot"):
            return None
        submission = super().process_form_submission(form)
        self._send_notification_email(form)
        self._send_confirmation_email(form)
        return submission

    def _send_notification_email(self, form):
        """Envoie le message au secrétariat."""
        from apps.core.services.emails import envoyer_notification_email

        data = form.cleaned_data
        lines = [f"{key}: {value}" for key, value in data.items() if key != "honeypot"]
        body = "\n".join(lines)

        envoyer_notification_email(
            sujet="Nouveau message via le site",
            titre="Nouveau message via le formulaire de contact",
            message=body,
            destinataires=[self.destinataire],
        )

    def _send_confirmation_email(self, form):
        """Envoie un accusé de réception au visiteur."""
        from apps.core.services.emails import envoyer_notification_email

        # Le libellé est éditable dans Wagtail : « Adresse email » devient par
        # exemple `adresse_email`. On identifie donc le champ par son type,
        # plutôt que par une courte liste de noms supposés.
        email = next(
            (
                form.cleaned_data.get(nom)
                for nom, champ in getattr(form, "fields", {}).items()
                if isinstance(champ, django_forms.EmailField) and form.cleaned_data.get(nom)
            ),
            None,
        )
        email = (
            email
            or form.cleaned_data.get("email")
            or form.cleaned_data.get("e-mail")
            or form.cleaned_data.get("courriel")
        )
        if not email:
            return
        envoyer_notification_email(
            sujet="Nous avons bien reçu votre message",
            titre="Nous avons bien reçu votre message",
            message=(
                "Bonjour,\n\n"
                "Nous avons bien reçu votre message et nous vous répondrons dans les meilleurs délais.\n\n"
                "Cordialement,\n"
                "Le secrétariat de l'ITEAG"
            ),
            destinataires=[email],
        )


# ──────────────────────────────────────────────
# Articles de recherche des enseignants
# ──────────────────────────────────────────────
# Modèles ordinaires, hors arborescence Wagtail : leurs auteurs les rédigent
# depuis leur espace enseignant, sans passer par l'admin du CMS.

from apps.website.models_publications import Article, ImageArticle  # noqa: E402,F401
