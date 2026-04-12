from django.db import models
from django.urls import reverse

from apps.core.models import TimeStampedModel


class Discipline(TimeStampedModel):
    """
    Grande famille de matières (5 disciplines ITEAG).
    AT, NT, Théologie systématique, Histoire de l'Église, Théologie pratique.
    """

    nom = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=120, unique=True)
    description = models.TextField(blank=True)
    ordre = models.PositiveSmallIntegerField(default=0, help_text="Ordre d'affichage")

    class Meta:
        verbose_name = "Discipline"
        verbose_name_plural = "Disciplines"
        ordering = ["ordre", "nom"]

    def __str__(self):
        return self.nom


class Parcours(TimeStampedModel):
    """
    Filière suivie par l'étudiant.
    CDC section 2.3 : diplômant ITEAG, bachelor FLTE, libre, ITEAG Pro.
    """

    class TypeParcours(models.TextChoices):
        DIPLOMANT_ITEAG = "diplomant_iteag", "Parcours diplômant ITEAG"
        BACHELOR_FLTE = "bachelor_flte", "Parcours Bachelor FLTE"
        LIBRE = "libre", "Parcours libre"
        PRO = "pro", "ITEAG Pro"

    nom = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200, unique=True)
    type_parcours = models.CharField(max_length=20, choices=TypeParcours.choices)
    description = models.TextField(blank=True)
    conditions_entree = models.TextField(blank=True, verbose_name="Conditions d'entrée")
    ects_requis = models.PositiveSmallIntegerField(default=180, verbose_name="ECTS requis")
    duree_annees = models.PositiveSmallIntegerField(default=6, verbose_name="Durée (années)")
    actif = models.BooleanField(default=True)

    # SEO
    meta_description = models.CharField(max_length=300, blank=True)

    class Meta:
        verbose_name = "Parcours"
        verbose_name_plural = "Parcours"
        ordering = ["nom"]

    def __str__(self):
        return self.nom

    def get_absolute_url(self):
        return reverse("formations:parcours_detail", kwargs={"slug": self.slug})


class Cours(TimeStampedModel):
    """
    Cours magistral. Chaque cours validé = 2.5 ECTS (CDC section 2.2).
    """

    titre = models.CharField(max_length=250)
    slug = models.SlugField(max_length=250, unique=True)
    code = models.CharField(max_length=20, blank=True, verbose_name="Code cours")
    discipline = models.ForeignKey(
        Discipline,
        on_delete=models.PROTECT,
        related_name="cours",
        verbose_name="Discipline",
    )
    parcours = models.ManyToManyField(Parcours, blank=True, related_name="cours")
    description = models.TextField(blank=True)
    objectifs = models.TextField(blank=True, verbose_name="Objectifs pédagogiques")
    ects = models.DecimalField(max_digits=4, decimal_places=1, default=2.5, verbose_name="ECTS")
    actif = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Cours"
        verbose_name_plural = "Cours"
        ordering = ["discipline", "titre"]

    def __str__(self):
        return f"{self.titre} ({self.discipline})"

    def get_absolute_url(self):
        return reverse("formations:cours_detail", kwargs={"slug": self.slug})


class Professeur(TimeStampedModel):
    """
    Fiche publique d'un enseignant — PUB-005.
    Lié optionnellement à un User si l'enseignant a un compte.
    """

    user = models.OneToOneField(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="profil_professeur",
    )
    nom = models.CharField(max_length=100)
    prenom = models.CharField(max_length=100, verbose_name="Prénom")
    slug = models.SlugField(max_length=200, unique=True)
    biographie = models.TextField(blank=True)
    specialite = models.CharField(max_length=200, blank=True, verbose_name="Spécialité")
    photo = models.ImageField(upload_to="professeurs/", blank=True)
    disciplines = models.ManyToManyField(Discipline, blank=True, related_name="professeurs")
    ordre = models.PositiveSmallIntegerField(default=0)
    actif = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Professeur"
        verbose_name_plural = "Professeurs"
        ordering = ["ordre", "nom"]

    def __str__(self):
        return f"{self.prenom} {self.nom}"

    @property
    def nom_complet(self):
        return f"{self.prenom} {self.nom}"


class Tarif(TimeStampedModel):
    """
    Grille tarifaire — CDC section 2.6.
    """

    class FormuleTarif(models.TextChoices):
        TOUTES_SESSIONS = "toutes", "Souscription à toutes les sessions"
        SESSION_CHOIX = "choix", "Souscription session au choix"

    class TypeMembre(models.TextChoices):
        EGLISE_FONDATRICE = "fondatrice", "Membre d'église fondatrice"
        AUTRE = "autre", "Autre"

    formule = models.CharField(max_length=20, choices=FormuleTarif.choices)
    type_membre = models.CharField(max_length=20, choices=TypeMembre.choices)
    montant_session = models.DecimalField(max_digits=8, decimal_places=2, verbose_name="Montant par session (€)")
    actif = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Tarif"
        verbose_name_plural = "Tarifs"
        unique_together = ["formule", "type_membre"]

    def __str__(self):
        return f"{self.get_formule_display()} — {self.get_type_membre_display()} : {self.montant_session} €"
