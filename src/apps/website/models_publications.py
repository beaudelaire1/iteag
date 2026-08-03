"""Articles de recherche rédigés par les enseignants.

Les enseignants de l'ITEAG sont des chercheurs, et n'avaient aucun moyen de
publier : les actualités passent par l'admin Wagtail, à laquelle ils n'ont pas
accès, et rien d'autre n'existait. Leurs travaux vivaient donc hors de la
plateforme, quand ils vivaient quelque part.

Le cycle reprend celui des modules e-learning, que le corps enseignant connaît
déjà : brouillon, soumis à relecture, publié. Rien ne paraît sous le nom de
l'institut sans un second regard — un article mal calibré, une fois indexé par
les moteurs, ne se retire pas d'un clic.

Le corps est du HTML **assaini à l'enregistrement**, jamais à l'affichage : ce
qui est en base est déjà propre, et une page qui oublierait le filtre ne
deviendrait pas pour autant vulnérable.
"""

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify

from apps.core.models import TimeStampedModel
from apps.core.services.redaction import assainir, en_texte


class Article(TimeStampedModel):
    """Un article de recherche signé par un enseignant."""

    class Statut(models.TextChoices):
        BROUILLON = "brouillon", "Brouillon"
        RELECTURE = "relecture", "Soumis à relecture"
        PUBLIE = "publie", "Publié"
        RETIRE = "retire", "Retiré"

    titre = models.CharField(max_length=250)
    sous_titre = models.CharField(max_length=300, blank=True, verbose_name="Sous-titre")
    slug = models.SlugField(max_length=280, unique=True, blank=True)

    auteur = models.ForeignKey(
        "formations.Professeur",
        on_delete=models.PROTECT,
        related_name="articles",
    )
    chapeau = models.TextField(
        blank=True,
        max_length=600,
        verbose_name="Chapeau",
        help_text="Deux ou trois phrases d'accroche, affichées dans les listes et les résultats de recherche.",
    )
    corps = models.TextField(blank=True, verbose_name="Corps de l'article")
    image_principale = models.ImageField(
        upload_to="articles/%Y/%m/",
        blank=True,
        verbose_name="Image à la une",
    )
    credit_image = models.CharField(max_length=200, blank=True, verbose_name="Crédit de l'image")

    statut = models.CharField(max_length=20, choices=Statut.choices, default=Statut.BROUILLON)
    date_publication = models.DateTimeField(null=True, blank=True, verbose_name="Publié le")
    date_soumission = models.DateTimeField(null=True, blank=True, verbose_name="Soumis le")
    motif_refus = models.TextField(blank=True, verbose_name="Motif du renvoi en brouillon")
    relu_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="articles_relus",
    )

    mots_cles = models.CharField(
        max_length=250,
        blank=True,
        verbose_name="Mots-clés",
        help_text="Séparés par des virgules. Ils servent au référencement.",
    )

    class Meta:
        verbose_name = "Article de recherche"
        verbose_name_plural = "Articles de recherche"
        ordering = ["-date_publication", "-created_at"]
        indexes = [
            models.Index(fields=["statut", "-date_publication"]),
            models.Index(fields=["auteur", "statut"]),
        ]

    def __str__(self):
        return self.titre

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = self._slug_libre()
        # L'assainissement a lieu ici, et non dans la vue : quel que soit le
        # chemin d'écriture — formulaire, import, shell — ce qui entre en base
        # est passé par la liste blanche.
        self.corps = assainir(self.corps)
        super().save(*args, **kwargs)

    def _slug_libre(self) -> str:
        racine = slugify(self.titre)[:250] or "article"
        candidat, rang = racine, 2
        while Article.objects.filter(slug=candidat).exclude(pk=self.pk).exists():
            candidat = f"{racine}-{rang}"
            rang += 1
        return candidat

    def get_absolute_url(self):
        return reverse("website:article_detail", kwargs={"slug": self.slug})

    # ── Cycle de vie ──

    @property
    def est_public(self) -> bool:
        return self.statut == self.Statut.PUBLIE

    @property
    def est_modifiable(self) -> bool:
        """Un article publié se retire avant d'être repris.

        Le modifier en place changerait sous les yeux du lecteur une page déjà
        indexée, sans que personne ne l'ait relue.
        """
        return self.statut in (self.Statut.BROUILLON, self.Statut.RETIRE)

    @property
    def resume(self) -> str:
        return self.chapeau or en_texte(self.corps, limite=200)

    def soumettre(self):
        from django.core.exceptions import ValidationError

        if self.statut not in (self.Statut.BROUILLON, self.Statut.RETIRE):
            raise ValidationError("Cet article est déjà soumis ou publié.")
        if not self.titre.strip() or not en_texte(self.corps).strip():
            raise ValidationError("Un article soumis doit avoir un titre et un corps.")
        self.statut = self.Statut.RELECTURE
        self.date_soumission = timezone.now()
        self.motif_refus = ""
        self.save(update_fields=["statut", "date_soumission", "motif_refus", "updated_at"])
        return self

    def publier(self, *, par=None):
        from django.core.exceptions import ValidationError

        if self.statut != self.Statut.RELECTURE:
            raise ValidationError("Seul un article soumis à relecture peut être publié.")
        self.statut = self.Statut.PUBLIE
        self.date_publication = self.date_publication or timezone.now()
        self.relu_par = par
        self.save(update_fields=["statut", "date_publication", "relu_par", "updated_at"])
        return self

    def renvoyer_en_brouillon(self, motif: str, *, par=None):
        """Le relecteur refuse : sans motif, l'auteur ne sait pas quoi corriger."""
        from django.core.exceptions import ValidationError

        motif = (motif or "").strip()
        if self.statut != self.Statut.RELECTURE:
            raise ValidationError("Seul un article en relecture peut être renvoyé à son auteur.")
        if not motif:
            raise ValidationError("Indiquez ce qui doit être repris.")
        self.statut = self.Statut.BROUILLON
        self.motif_refus = motif
        self.relu_par = par
        self.save(update_fields=["statut", "motif_refus", "relu_par", "updated_at"])
        return self

    def retirer(self, *, par=None):
        """Dépublie sans détruire : l'article redevient modifiable."""
        from django.core.exceptions import ValidationError

        if self.statut != self.Statut.PUBLIE:
            raise ValidationError("Seul un article publié peut être retiré.")
        self.statut = self.Statut.RETIRE
        self.relu_par = par
        self.save(update_fields=["statut", "relu_par", "updated_at"])
        return self


class ImageArticle(TimeStampedModel):
    """Une illustration déposée pour être insérée dans le corps d'un article.

    Elles vivent à part de l'image à la une : un article de recherche porte
    volontiers des figures, des tableaux photographiés ou des cartes, et
    l'auteur doit pouvoir les déposer puis les placer où il veut dans le texte.
    """

    article = models.ForeignKey(Article, on_delete=models.CASCADE, related_name="illustrations")
    fichier = models.ImageField(upload_to="articles/illustrations/%Y/%m/")
    legende = models.CharField(max_length=250, blank=True, verbose_name="Légende")

    class Meta:
        verbose_name = "Illustration d'article"
        verbose_name_plural = "Illustrations d'article"
        ordering = ["created_at"]

    def __str__(self):
        return self.legende or self.fichier.name.rsplit("/", 1)[-1]
