from django.db import models

from apps.core.models import TimeStampedModel


class ReglementInscription(TimeStampedModel):
    """Relie un règlement en ligne à la demande d'inscription qu'il solde."""

    reglement = models.OneToOneField(
        "paiements.Reglement",
        on_delete=models.CASCADE,
        related_name="inscription_associee",
        verbose_name="Règlement",
    )
    demande = models.OneToOneField(
        "academics.DemandeInscriptionCours",
        on_delete=models.PROTECT,
        related_name="reglement_en_ligne",
        verbose_name="Demande d'inscription",
    )

    class Meta:
        verbose_name = "Règlement d'inscription"
        verbose_name_plural = "Règlements d'inscription"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.demande} — {self.reglement}"
