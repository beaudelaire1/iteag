from django.conf import settings
from django.db import models

from apps.core.models import TimeStampedModel


class DocumentAdministratif(TimeStampedModel):
    """Document PDF généré — CDC ETU-008 / ADM-009."""

    class TypeDocument(models.TextChoices):
        ATTESTATION = "attestation", "Attestation d'inscription"
        RELEVE_NOTES = "releve_notes", "Relevé de notes"
        CERTIFICAT = "certificat", "Certificat de scolarité"
        RECU = "recu", "Reçu de paiement"

    etudiant = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="documents_administratifs",
        limit_choices_to={"role": "etudiant"},
    )
    type_document = models.CharField(
        max_length=20,
        choices=TypeDocument.choices,
        verbose_name="Type de document",
    )
    fichier_pdf = models.FileField(
        upload_to="documents/%Y/%m/",
        blank=True,
        verbose_name="Fichier PDF",
    )
    date_generation = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Date de génération",
    )

    class Meta:
        verbose_name = "Document administratif"
        verbose_name_plural = "Documents administratifs"
        ordering = ["-date_generation"]

    def __str__(self):
        return f"{self.get_type_document_display()} — {self.etudiant}"
