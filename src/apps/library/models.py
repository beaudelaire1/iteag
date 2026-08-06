from django.conf import settings
from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVector, SearchVectorField
from django.db import models

from apps.core.models import TimeStampedModel


class NoticeBibliographique(TimeStampedModel):
    """
    Notice bibliographique — CDC BIB-001.
    2 635+ ouvrages catalogués de la bibliothèque ITEAG.
    """

    titre = models.CharField(max_length=500)
    auteur = models.CharField(max_length=300, blank=True)
    editeur = models.CharField(max_length=200, blank=True, verbose_name="Éditeur")
    date_publication = models.CharField(max_length=50, blank=True, verbose_name="Date de publication")
    isbn = models.CharField(max_length=20, blank=True, verbose_name="ISBN")
    mots_cles = models.TextField(blank=True, verbose_name="Mots-clés", help_text="Mots-clés séparés par des virgules")
    cote = models.CharField(max_length=50, blank=True, verbose_name="Cote")
    discipline = models.ForeignKey(
        "formations.Discipline",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notices",
    )
    description = models.TextField(blank=True, verbose_name="Résumé / description")
    disponible = models.BooleanField(default=True, verbose_name="Disponible en bibliothèque")

    # Recherche full-text PostgreSQL
    search_vector = SearchVectorField(null=True, blank=True)

    class Meta:
        verbose_name = "Notice bibliographique"
        verbose_name_plural = "Notices bibliographiques"
        ordering = ["titre"]
        indexes = [
            models.Index(fields=["titre"]),
            models.Index(fields=["auteur"]),
            models.Index(fields=["cote"]),
            GinIndex(fields=["search_vector"], name="library_search_gin"),
        ]

    def __str__(self):
        if self.auteur:
            return f"{self.titre} — {self.auteur}"
        return self.titre

    @property
    def mots_cles_list(self):
        if self.mots_cles:
            return [kw.strip() for kw in self.mots_cles.split(",") if kw.strip()]
        return []

    def save(self, *args, **kwargs):
        from django.db import connection

        super().save(*args, **kwargs)
        # Mise à jour du search_vector via SQL pour bénéficier de la config 'french'
        if connection.vendor == "postgresql":
            NoticeBibliographique.objects.filter(pk=self.pk).update(search_vector=self.vecteur_de_recherche())

    @staticmethod
    def vecteur_de_recherche():
        """Cote et ISBN en font partie : ce sont eux qu'un bibliothécaire tape."""
        return (
            SearchVector("titre", weight="A", config="french")
            + SearchVector("auteur", weight="A", config="french")
            + SearchVector("cote", weight="A", config="french")
            + SearchVector("isbn", weight="B", config="french")
            + SearchVector("mots_cles", weight="B", config="french")
            + SearchVector("description", weight="C", config="french")
        )


class Emprunt(TimeStampedModel):
    """
    Suivi d'un prêt ou d'une réservation d'ouvrage physique de la bibliothèque.
    """

    class Statut(models.TextChoices):
        RESERVE = "reserve", "Réservé"
        EN_COURS = "en_cours", "En cours"
        RENDU = "rendu", "Rendu"
        EN_RETARD = "en_retard", "En retard"

    notice = models.ForeignKey(
        NoticeBibliographique,
        on_delete=models.CASCADE,
        related_name="emprunts",
        verbose_name="Ouvrage",
    )
    emprunteur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="emprunts_bibliotheque",
        verbose_name="Emprunteur",
    )
    statut = models.CharField(
        max_length=20,
        choices=Statut.choices,
        default=Statut.RESERVE,
        verbose_name="Statut du prêt",
    )
    date_retrait = models.DateTimeField(null=True, blank=True, verbose_name="Date de retrait effectif")
    date_retour_prevue = models.DateField(verbose_name="Date de retour prévue")
    date_retour_effectif = models.DateField(null=True, blank=True, verbose_name="Date de retour effectif")
    commentaire = models.TextField(blank=True, verbose_name="Remarques / état de l'ouvrage")

    class Meta:
        verbose_name = "Emprunt de bibliothèque"
        verbose_name_plural = "Emprunts de bibliothèque"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["statut", "-created_at"]),
            models.Index(fields=["emprunteur", "statut"]),
        ]

    def __str__(self):
        return f"{self.notice.titre} — {self.emprunteur} ({self.get_statut_display()})"
