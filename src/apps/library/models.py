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
            NoticeBibliographique.objects.filter(pk=self.pk).update(
                search_vector=(
                    SearchVector("titre", weight="A", config="french")
                    + SearchVector("auteur", weight="A", config="french")
                    + SearchVector("mots_cles", weight="B", config="french")
                    + SearchVector("description", weight="C", config="french")
                )
            )
