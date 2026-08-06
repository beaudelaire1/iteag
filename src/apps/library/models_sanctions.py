from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models import TimeStampedModel


class SuspensionBibliotheque(TimeStampedModel):
    """Interdiction temporaire de nouvel emprunt après une restitution tardive."""

    emprunteur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="suspensions_bibliotheque",
        verbose_name="Emprunteur",
    )
    emprunt = models.OneToOneField(
        "library.Emprunt",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sanction",
        verbose_name="Emprunt à l'origine",
    )
    jours_retard = models.PositiveIntegerField(verbose_name="Jours de retard")
    jours_suspension = models.PositiveIntegerField(verbose_name="Jours de suspension")
    date_debut = models.DateField(verbose_name="Début de suspension")
    date_fin = models.DateField(verbose_name="Fin de suspension")
    levee_le = models.DateTimeField(null=True, blank=True, verbose_name="Levée le")
    levee_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="suspensions_bibliotheque_levees",
        verbose_name="Levée par",
    )
    motif_levee = models.TextField(blank=True, verbose_name="Motif de la levée")

    class Meta:
        verbose_name = "Suspension de bibliothèque"
        verbose_name_plural = "Suspensions de bibliothèque"
        ordering = ["-date_debut", "-created_at"]
        indexes = [
            models.Index(fields=["emprunteur", "date_fin"]),
            models.Index(fields=["levee_le", "date_fin"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(jours_retard__gt=0),
                name="library_suspension_retard_positif",
            ),
            models.CheckConstraint(
                condition=models.Q(jours_suspension__gt=0),
                name="library_suspension_duree_positive",
            ),
            models.CheckConstraint(
                condition=models.Q(date_fin__gte=models.F("date_debut")),
                name="library_suspension_dates_valides",
            ),
        ]

    def __str__(self):
        return f"{self.emprunteur} — suspendu jusqu'au {self.date_fin:%d/%m/%Y}"

    @property
    def est_active(self) -> bool:
        return self.levee_le is None and self.date_fin >= timezone.localdate()
