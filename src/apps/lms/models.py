from django.conf import settings
from django.db import models

from apps.core.models import TimeStampedModel


class RessourcePedagogique(TimeStampedModel):
    """
    Fichier/document pédagogique déposé par un enseignant — ENS-002.
    Rattaché à un cours de session.
    """

    cours_session = models.ForeignKey(
        "academics.CoursDeSession",
        on_delete=models.CASCADE,
        related_name="ressources",
    )
    titre = models.CharField(max_length=250)
    description = models.TextField(blank=True)
    fichier = models.FileField(upload_to="lms/ressources/%Y/%m/")
    type_fichier = models.CharField(max_length=50, blank=True, help_text="PDF, DOCX, PPT, etc.")
    taille = models.PositiveIntegerField(default=0, help_text="Taille en octets")
    uploade_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="ressources_uploadees",
    )
    visible_etudiants = models.BooleanField(default=True, verbose_name="Visible par les étudiants")

    class Meta:
        verbose_name = "Ressource pédagogique"
        verbose_name_plural = "Ressources pédagogiques"
        ordering = ["-created_at"]

    def __str__(self):
        return self.titre

    def save(self, *args, **kwargs):
        if self.fichier and not self.taille:
            self.taille = self.fichier.size
        if self.fichier and not self.type_fichier:
            self.type_fichier = self.fichier.name.rsplit(".", 1)[-1].upper() if "." in self.fichier.name else ""
        super().save(*args, **kwargs)


class Evaluation(TimeStampedModel):
    """
    Évaluation d'un étudiant sur un cours de session — CDC section 9.1.
    Workflow : EN_ATTENTE → SOUMIS → EN_CORRECTION → NOTÉ → PUBLIÉ.
    """

    class TypeEvaluation(models.TextChoices):
        DEVOIR = "devoir", "Devoir"
        EXAMEN = "examen", "Examen"
        STAGE = "stage", "Stage"
        DISSERTATION = "dissertation", "Dissertation de fin d'études"
        VAE = "vae", "VAE"

    class StatutEvaluation(models.TextChoices):
        EN_ATTENTE = "en_attente", "En attente"
        SOUMIS = "soumis", "Soumis"
        EN_CORRECTION = "en_correction", "En correction"
        NOTE = "note", "Noté"
        PUBLIE = "publie", "Publié"

    etudiant = models.ForeignKey(
        "academics.ProfilEtudiant",
        on_delete=models.CASCADE,
        related_name="evaluations",
    )
    cours_session = models.ForeignKey(
        "academics.CoursDeSession",
        on_delete=models.CASCADE,
        related_name="evaluations",
    )
    type_evaluation = models.CharField(max_length=20, choices=TypeEvaluation.choices, default=TypeEvaluation.DEVOIR)
    statut = models.CharField(max_length=20, choices=StatutEvaluation.choices, default=StatutEvaluation.EN_ATTENTE)

    # Soumission étudiant
    fichier_soumis = models.FileField(upload_to="lms/devoirs/%Y/%m/", blank=True, verbose_name="Fichier remis")
    date_soumission = models.DateTimeField(null=True, blank=True)

    # Notation enseignant
    note = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    appreciation = models.TextField(blank=True, verbose_name="Appréciation")
    ects_valides = models.DecimalField(
        max_digits=4,
        decimal_places=1,
        default=0,
        verbose_name="ECTS validés",
        help_text="0 ou 2.5",
    )
    date_notation = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Évaluation"
        verbose_name_plural = "Évaluations"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.etudiant} — {self.cours_session} ({self.get_statut_display()})"


class Annonce(TimeStampedModel):
    """Annonce enseignant pour un cours de session — ENS-006."""

    cours_session = models.ForeignKey(
        "academics.CoursDeSession",
        on_delete=models.CASCADE,
        related_name="annonces",
    )
    auteur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
    )
    titre = models.CharField(max_length=250)
    contenu = models.TextField()

    class Meta:
        verbose_name = "Annonce"
        verbose_name_plural = "Annonces"
        ordering = ["-created_at"]

    def __str__(self):
        return self.titre
