import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models import TimeStampedModel


class DossierCandidature(TimeStampedModel):
    """
    Dossier de candidature — CDC section 7.1.
    Workflow : SOUMIS → EN_EXAMEN → INCOMPLET/ACCEPTÉ/REFUSÉ.
    """

    class Statut(models.TextChoices):
        SOUMIS = "soumis", "Soumis"
        EN_EXAMEN = "en_examen", "En examen"
        INCOMPLET = "incomplet", "Incomplet"
        ACCEPTE = "accepte", "Accepté"
        REFUSE = "refuse", "Refusé"

    # Identité candidat
    nom = models.CharField(max_length=100)
    prenom = models.CharField(max_length=100, verbose_name="Prénom")
    email = models.EmailField()
    telephone = models.CharField(max_length=20, blank=True, verbose_name="Téléphone")
    date_naissance = models.DateField(null=True, blank=True, verbose_name="Date de naissance")

    # Candidature
    parcours_souhaite = models.ForeignKey(
        "formations.Parcours",
        on_delete=models.PROTECT,
        verbose_name="Parcours souhaité",
    )
    motivations = models.TextField(verbose_name="Lettre de motivation")
    eglise = models.CharField(max_length=200, blank=True, verbose_name="Église d'appartenance")
    eglise_fondatrice = models.BooleanField(default=False, verbose_name="Membre d'une église fondatrice ?")

    # Pièces jointes
    piece_identite = models.FileField(upload_to="candidatures/identite/", blank=True, verbose_name="Pièce d'identité")
    diplomes = models.FileField(upload_to="candidatures/diplomes/", blank=True, verbose_name="Diplômes")
    autre_document = models.FileField(upload_to="candidatures/autres/", blank=True, verbose_name="Autre document")

    # Workflow
    statut = models.CharField(max_length=20, choices=Statut.choices, default=Statut.SOUMIS)
    date_soumission = models.DateTimeField(default=timezone.now)
    date_derniere_maj = models.DateTimeField(auto_now=True)
    motif_refus = models.TextField(blank=True, verbose_name="Motif du refus")
    notes_internes = models.TextField(blank=True, verbose_name="Notes internes (secrétariat)")
    elements_manquants = models.TextField(blank=True, verbose_name="Éléments manquants")

    # Suivi public (lien signé)
    token_suivi = models.CharField(max_length=64, unique=True, editable=False)

    # Lien vers l'utilisateur créé après acceptation
    utilisateur_cree = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="candidature",
    )

    class Meta:
        verbose_name = "Dossier de candidature"
        verbose_name_plural = "Dossiers de candidature"
        ordering = ["-date_soumission"]

    def __str__(self):
        return f"{self.prenom} {self.nom} — {self.get_statut_display()}"

    def save(self, *args, **kwargs):
        if not self.token_suivi:
            self.token_suivi = secrets.token_urlsafe(48)
        super().save(*args, **kwargs)

    @property
    def nom_complet(self):
        return f"{self.prenom} {self.nom}"


class HistoriqueStatut(TimeStampedModel):
    """Journal des changements de statut d'un dossier."""

    dossier = models.ForeignKey(
        DossierCandidature,
        on_delete=models.CASCADE,
        related_name="historique",
    )
    ancien_statut = models.CharField(max_length=20, choices=DossierCandidature.Statut.choices)
    nouveau_statut = models.CharField(max_length=20, choices=DossierCandidature.Statut.choices)
    modifie_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
    )
    commentaire = models.TextField(blank=True)

    class Meta:
        verbose_name = "Historique de statut"
        verbose_name_plural = "Historique des statuts"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.dossier} : {self.ancien_statut} → {self.nouveau_statut}"
