import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models import TimeStampedModel


class PieceComplementaire(TimeStampedModel):
    """
    Une pièce réclamée à un candidat en cours d'instruction.

    Le dossier ne portait que trois champs fichier figés — identité, diplômes,
    autre document. Dès que le secrétariat avait besoin d'autre chose — un
    relevé de notes, une attestation d'église, une traduction — il n'existait
    aucun moyen de le demander : la seule voie était un courriel hors
    plateforme, sans trace, sans relance, et sans endroit où déposer la
    réponse. La candidature restait « incomplète » sans que personne ne sache
    de quoi.

    Chaque pièce est donc un objet : elle est demandée, elle est déposée, elle
    est acceptée ou refusée avec un motif. L'état du dossier se lit alors sans
    rien reconstituer.
    """

    class Statut(models.TextChoices):
        DEMANDEE = "demandee", "Demandée"
        DEPOSEE = "deposee", "Déposée, en attente de vérification"
        VALIDEE = "validee", "Validée"
        REFUSEE = "refusee", "Refusée, à redéposer"

    dossier = models.ForeignKey(
        "DossierCandidature",
        on_delete=models.CASCADE,
        related_name="pieces_complementaires",
    )
    libelle = models.CharField(max_length=200, verbose_name="Pièce demandée")
    description = models.TextField(
        blank=True,
        verbose_name="Précisions",
        help_text="Ce que le candidat doit fournir exactement. Une demande vague revient deux fois.",
    )
    obligatoire = models.BooleanField(
        default=True,
        help_text="Une pièce facultative n'empêche pas l'instruction du dossier.",
    )
    statut = models.CharField(max_length=20, choices=Statut.choices, default=Statut.DEMANDEE)

    fichier = models.FileField(upload_to="candidatures/complements/%Y/%m/", blank=True)
    motif_refus = models.TextField(blank=True, verbose_name="Motif du refus")

    demandee_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pieces_demandees",
    )
    date_depot = models.DateTimeField(null=True, blank=True, verbose_name="Déposée le")
    date_verification = models.DateTimeField(null=True, blank=True, verbose_name="Vérifiée le")

    class Meta:
        verbose_name = "Pièce complémentaire"
        verbose_name_plural = "Pièces complémentaires"
        ordering = ["created_at"]
        indexes = [models.Index(fields=["dossier", "statut"])]

    def __str__(self):
        return f"{self.libelle} — {self.dossier}"

    @property
    def est_en_attente(self) -> bool:
        """Le candidat doit-il encore agir ?"""
        return self.statut in (self.Statut.DEMANDEE, self.Statut.REFUSEE)

    @property
    def bloque_le_dossier(self) -> bool:
        return self.obligatoire and self.statut != self.Statut.VALIDEE


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
