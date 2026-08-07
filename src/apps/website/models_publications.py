"""Articles de recherche et contenus éditoriaux publics hors arborescence Wagtail."""

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify
from wagtail.fields import StreamField

from apps.core.models import TimeStampedModel
from apps.core.services.redaction import assainir, en_texte
from apps.website.editorial import CorpsActualiteBlock


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
    retrait_demande_le = models.DateTimeField(null=True, blank=True, verbose_name="Retrait demandé le")
    motif_retrait = models.TextField(blank=True, verbose_name="Motif de la demande de retrait")
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
        verbose_name = "Article"
        verbose_name_plural = "Articles"
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

    @property
    def est_public(self) -> bool:
        return self.statut == self.Statut.PUBLIE

    @property
    def est_modifiable(self) -> bool:
        return self.statut in (self.Statut.BROUILLON, self.Statut.RETIRE)

    @property
    def est_supprimable(self) -> bool:
        return self.statut in (self.Statut.BROUILLON, self.Statut.RETIRE)

    @property
    def retrait_demande(self) -> bool:
        return self.est_public and self.retrait_demande_le is not None

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
        self.retrait_demande_le = None
        self.motif_retrait = ""
        self.save(
            update_fields=[
                "statut",
                "date_soumission",
                "motif_refus",
                "retrait_demande_le",
                "motif_retrait",
                "updated_at",
            ]
        )
        return self

    def demander_le_retrait(self, motif: str):
        from django.core.exceptions import ValidationError

        motif = (motif or "").strip()
        if self.statut != self.Statut.PUBLIE:
            raise ValidationError("Seul un article publié fait l'objet d'une demande de retrait.")
        if not motif:
            raise ValidationError("Indiquez pourquoi cet article doit être retiré.")
        self.retrait_demande_le = timezone.now()
        self.motif_retrait = motif
        self.save(update_fields=["retrait_demande_le", "motif_retrait", "updated_at"])
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
        from django.core.exceptions import ValidationError

        if self.statut != self.Statut.PUBLIE:
            raise ValidationError("Seul un article publié peut être retiré.")
        self.statut = self.Statut.RETIRE
        self.relu_par = par
        self.retrait_demande_le = None
        self.motif_retrait = ""
        self.save(update_fields=["statut", "relu_par", "retrait_demande_le", "motif_retrait", "updated_at"])
        return self


class ImageArticle(TimeStampedModel):
    """Une illustration déposée pour être insérée dans le corps d'un article."""

    article = models.ForeignKey(Article, on_delete=models.CASCADE, related_name="illustrations")
    fichier = models.ImageField(upload_to="articles/illustrations/%Y/%m/")
    legende = models.CharField(max_length=250, blank=True, verbose_name="Légende")

    class Meta:
        verbose_name = "Illustration d'article"
        verbose_name_plural = "Illustrations d'article"
        ordering = ["created_at"]

    def __str__(self):
        return self.legende or self.fichier.name.rsplit("/", 1)[-1]


class ContenuActualite(models.Model):
    """Corps structuré d'une page d'actualité existante.

    Le RichText historique de ``NewsPage.body`` reste en place comme filet de
    sécurité. Une migration copie chaque ancien corps dans un premier bloc
    texte ; aucun article existant n'est donc converti de force en JSON.
    """

    actualite = models.OneToOneField(
        "website.NewsPage",
        on_delete=models.CASCADE,
        related_name="contenu_structure",
    )
    contenu = StreamField(
        CorpsActualiteBlock(),
        blank=True,
        use_json_field=True,
        verbose_name="Contenu structuré",
    )

    class Meta:
        verbose_name = "Contenu structuré d'actualité"
        verbose_name_plural = "Contenus structurés d'actualités"

    def __str__(self):
        return self.actualite.title


class TemoignageEtudiant(models.Model):
    """Témoignage proposé par un étudiant et publié uniquement par la direction."""

    class Statut(models.TextChoices):
        EN_ATTENTE = "en_attente", "En attente"
        PUBLIE = "publie", "Publié"
        REFUSE = "refuse", "Refusé"
        RETIRE = "retire", "Retiré"

    etudiant = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="temoignage_iteag",
        limit_choices_to={"role": "etudiant"},
        verbose_name="Étudiant",
    )
    nom_affiche = models.CharField(max_length=160, verbose_name="Nom affiché")
    promotion = models.CharField(max_length=160, blank=True, verbose_name="Promotion / parcours")
    texte = models.TextField(max_length=6000, verbose_name="Témoignage")
    photo = models.ImageField(
        upload_to="temoignages/%Y/%m/",
        blank=True,
        verbose_name="Photo du témoignage",
        help_text="Photo facultative choisie spécifiquement pour l'affichage public du témoignage.",
    )
    consentement_publication = models.BooleanField(default=False, verbose_name="Consentement à la publication")
    statut = models.CharField(max_length=20, choices=Statut.choices, default=Statut.EN_ATTENTE, db_index=True)
    motif_refus = models.CharField(max_length=500, blank=True, verbose_name="Motif du refus")
    soumis_le = models.DateTimeField(auto_now_add=True)
    modifie_le = models.DateTimeField(auto_now=True)
    valide_le = models.DateTimeField(null=True, blank=True)
    valide_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="temoignages_valides",
        verbose_name="Validé par",
    )

    class Meta:
        verbose_name = "Témoignage étudiant"
        verbose_name_plural = "Témoignages étudiants"
        ordering = ["-soumis_le"]

    def __str__(self):
        return f"{self.nom_affiche} — {self.get_statut_display()}"

    def save(self, *args, **kwargs):
        self.texte = assainir(self.texte)
        super().save(*args, **kwargs)

    @property
    def est_public(self) -> bool:
        return self.statut == self.Statut.PUBLIE and self.consentement_publication
