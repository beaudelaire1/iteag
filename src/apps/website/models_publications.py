"""Articles de recherche et contenus éditoriaux publics hors arborescence Wagtail."""

import mimetypes
from pathlib import Path

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
    """Un article signé par un enseignant ou un étudiant."""

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
        null=True,
        blank=True,
        related_name="articles",
    )
    auteur_etudiant = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="articles_rediges",
        limit_choices_to={"role": "etudiant"},
        verbose_name="Auteur étudiant",
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
            models.Index(
                fields=["auteur_etudiant", "statut"],
                name="website_ar_auteur__30c162_idx",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(auteur__isnull=False, auteur_etudiant__isnull=True)
                    | models.Q(auteur__isnull=True, auteur_etudiant__isnull=False)
                ),
                name="article_exactement_un_auteur",
            ),
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
    def utilisateur_auteur(self):
        if self.auteur_etudiant_id:
            return self.auteur_etudiant
        if self.auteur_id:
            return self.auteur.user
        return None

    @property
    def nom_auteur(self) -> str:
        if self.auteur_id:
            return self.auteur.nom_complet
        if self.auteur_etudiant_id:
            return self.auteur_etudiant.get_full_name() or self.auteur_etudiant.username
        return "Auteur inconnu"

    @property
    def qualite_auteur(self) -> str:
        if self.auteur_id:
            return self.auteur.specialite
        return "Étudiant de l'ITEAG"

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


# ──────────────────────────────────────────────
# Brochures — documents de communication publiés
# ──────────────────────────────────────────────


class Brochure(TimeStampedModel):
    """Un document de communication mis à disposition du public.

    Une brochure n'est pas un document rédigé : elle n'a ni destinataire, ni
    référence au registre, et elle n'est pas composée dans l'application. Elle
    arrive mise en page depuis l'imprimeur ou le graphiste, et ce qu'on attend
    du site est de la porter — pas de la réécrire.

    Une brochure se joint déjà à une actualité (« NewsPage.brochure »), et cela
    reste le bon geste pour annoncer : « voici le programme de la rentrée », le
    PDF sous le texte. Mais l'annonce passe, et le document reste. Six mois plus
    tard, la plaquette d'admission n'est plus retrouvable que par celui qui se
    souvient de l'actualité qui la portait — et le visiteur venu chercher « les
    brochures de l'institut » n'a aucune page où aller.

    Ce modèle sert cet autre besoin : un catalogue durable, classé, que le
    secrétariat alimente depuis sa rubrique et que le public consulte
    directement. Les deux chemins coexistent sans se gêner.

    Le fichier reste en place tant que la brochure existe : dépublier ne
    supprime rien, cela retire seulement l'adresse publique. Une plaquette de
    l'an dernier qu'on remet en ligne pour une réunion doit se retrouver
    intacte, pas se re-téléverser.
    """

    class Categorie(models.TextChoices):
        INSTITUTION = "institution", "Présentation de l'institut"
        FORMATION = "formation", "Formation ou parcours"
        ADMISSION = "admission", "Admission et inscription"
        EVENEMENT = "evenement", "Événement"
        AUTRE = "autre", "Autre document"

    class Statut(models.TextChoices):
        BROUILLON = "brouillon", "Brouillon"
        PUBLIEE = "publiee", "Publiée"

    titre = models.CharField(max_length=200, verbose_name="Titre")
    slug = models.SlugField(max_length=220, unique=True, blank=True)
    description = models.TextField(
        blank=True,
        max_length=600,
        verbose_name="Description",
        help_text="Deux ou trois phrases : ce que le visiteur trouvera dans le document.",
    )
    categorie = models.CharField(
        max_length=20,
        choices=Categorie.choices,
        default=Categorie.INSTITUTION,
        db_index=True,
        verbose_name="Catégorie",
    )
    fichier = models.FileField(upload_to="brochures/%Y/%m/", verbose_name="Fichier de la brochure")
    couverture = models.ImageField(
        upload_to="brochures/couvertures/%Y/%m/",
        blank=True,
        verbose_name="Image de couverture",
    )

    statut = models.CharField(max_length=20, choices=Statut.choices, default=Statut.BROUILLON, db_index=True)
    date_publication = models.DateTimeField(null=True, blank=True, verbose_name="Publiée le")
    # Le classement de la page publique est décidé par le secrétariat, pas par
    # la date de dépôt : la brochure institutionnelle doit rester en tête même
    # quand une plaquette d'événement arrive après elle.
    ordre = models.PositiveIntegerField(
        default=0,
        verbose_name="Ordre d'affichage",
        help_text="Les plus petits nombres passent en premier. Laissez 0 pour un classement par date.",
    )
    nombre_telechargements = models.PositiveIntegerField(default=0, verbose_name="Téléchargements")

    deposee_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="brochures_deposees",
        verbose_name="Déposée par",
    )

    class Meta:
        verbose_name = "Brochure"
        verbose_name_plural = "Brochures"
        ordering = ["ordre", "-date_publication", "-created_at"]
        indexes = [models.Index(fields=["statut", "ordre"])]

    def __str__(self):
        return self.titre

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = self._slug_libre(self.titre)
        super().save(*args, **kwargs)

    @staticmethod
    def _slug_libre(titre: str) -> str:
        base = slugify(titre)[:200] or "brochure"
        candidat, suffixe = base, 1
        while Brochure.objects.filter(slug=candidat).exists():
            suffixe += 1
            candidat = f"{base}-{suffixe}"
        return candidat

    def get_absolute_url(self) -> str:
        return reverse("website:brochure_telecharger", kwargs={"slug": self.slug})

    @property
    def url_sur_le_site(self) -> str:
        """La page où le visiteur la trouve, et l'endroit exact où elle s'y trouve.

        « get_absolute_url » sert le fichier : la suivre télécharge le document
        sans jamais montrer la page qui le porte. Publier ne disait donc rien de
        l'endroit où la brochure venait d'apparaître — le secrétariat savait
        qu'elle était en ligne, et rien d'autre.
        """
        return f"{reverse('website:brochures')}#brochure-{self.slug}"

    @property
    def est_publiee(self) -> bool:
        return self.statut == self.Statut.PUBLIEE

    @property
    def extension(self) -> str:
        """L'extension réelle du document déposé, point compris."""
        return Path(self.fichier.name).suffix.lower() if self.fichier else ""

    @property
    def format_lisible(self) -> str:
        """Ce qu'on annonce au visiteur avant qu'il clique — « PDF », « DOCX »."""
        return self.extension.lstrip(".").upper()

    @property
    def est_image(self) -> bool:
        """L'affiche déposée telle quelle, plutôt qu'un document à ouvrir.

        Une affiche arrive souvent en photo. Le site n'a alors rien à faire
        télécharger : l'image *est* la brochure, et elle se montre.
        """
        return self.extension in {".jpg", ".jpeg", ".png"}

    @property
    def apercu_url(self) -> str:
        """L'image à montrer sur la page publique, s'il y en a une.

        La couverture prime quand elle existe — c'est un choix éditorial. À
        défaut, une brochure qui est elle-même une image s'illustre toute
        seule : réclamer une couverture pour une affiche reviendrait à
        redemander la même image deux fois.
        """
        if self.couverture:
            return self.couverture.url
        if self.est_image and self.fichier:
            return self.fichier.url
        return ""

    @property
    def type_mime(self) -> str:
        """Le type à servir.

        Depuis que la brochure accepte aussi le bureautique, annoncer
        « application/pdf » pour tout ferait télécharger un DOCX que le
        navigateur essaierait d'afficher comme un PDF, et qui s'ouvrirait sur
        une erreur. On déduit donc le type de l'extension, déjà contrôlée par
        la signature binaire au dépôt.
        """
        devine, _ = mimetypes.guess_type(self.fichier.name if self.fichier else "")
        return devine or "application/octet-stream"

    @property
    def taille_lisible(self) -> str:
        """Le poids du fichier, tel qu'on l'annonce avant un téléchargement.

        Un fichier absent du stockage — restauration partielle, média non
        monté — ne doit pas casser la page qui le liste : on préfère ne rien
        annoncer plutôt que lever une erreur au rendu.
        """
        try:
            octets = self.fichier.size
        except (ValueError, OSError):
            return ""
        if octets < 1024 * 1024:
            return f"{max(1, round(octets / 1024))} Ko"
        return f"{octets / (1024 * 1024):.1f} Mo".replace(".", ",")

    def publier(self, *, maintenant=None) -> None:
        self.statut = self.Statut.PUBLIEE
        self.date_publication = maintenant or timezone.now()
        self.save(update_fields=["statut", "date_publication", "updated_at"])

    def depublier(self) -> None:
        """Retire la brochure du site sans toucher au fichier ni à sa date.

        La date de première publication est conservée : elle sert de repère au
        secrétariat pour savoir depuis quand le document circule.
        """
        self.statut = self.Statut.BROUILLON
        self.save(update_fields=["statut", "updated_at"])
