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

    nom = models.CharField(max_length=100)
    prenom = models.CharField(max_length=100, verbose_name="Prénom")
    email = models.EmailField()
    telephone = models.CharField(max_length=20, blank=True, verbose_name="Téléphone")
    date_naissance = models.DateField(null=True, blank=True, verbose_name="Date de naissance")

    parcours_souhaite = models.ForeignKey(
        "formations.Parcours",
        on_delete=models.PROTECT,
        verbose_name="Parcours souhaité",
    )
    motivations = models.TextField(verbose_name="Lettre de motivation")
    eglise = models.CharField(max_length=200, blank=True, verbose_name="Église d'appartenance")
    eglise_fondatrice = models.BooleanField(default=False, verbose_name="Membre d'une église fondatrice ?")

    piece_identite = models.FileField(upload_to="candidatures/identite/", blank=True, verbose_name="Pièce d'identité")
    diplomes = models.FileField(upload_to="candidatures/diplomes/", blank=True, verbose_name="Diplômes")
    autre_document = models.FileField(upload_to="candidatures/autres/", blank=True, verbose_name="Autre document")

    statut = models.CharField(max_length=20, choices=Statut.choices, default=Statut.SOUMIS)
    date_soumission = models.DateTimeField(default=timezone.now)
    date_derniere_maj = models.DateTimeField(auto_now=True)
    motif_refus = models.TextField(blank=True, verbose_name="Motif du refus")
    notes_internes = models.TextField(blank=True, verbose_name="Notes internes (secrétariat)")
    elements_manquants = models.TextField(blank=True, verbose_name="Éléments manquants")

    token_suivi = models.CharField(max_length=64, unique=True, editable=False)

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


class DemandePieces(TimeStampedModel):
    """Une demande cohérente contenant une ou plusieurs pièces justificatives.

    Le message, l'échéance, le dépôt et la décision appartiennent au lot. Les
    fichiers restent séparés pour conserver leur libellé, leur état et, en cas
    de refus partiel, leur motif propre.
    """

    class Statut(models.TextChoices):
        A_FOURNIR = "a_fournir", "À fournir"
        A_VERIFIER = "a_verifier", "Déposée — à vérifier"
        A_CORRIGER = "a_corriger", "À corriger"
        VALIDEE = "validee", "Validée"

    dossier = models.ForeignKey(
        DossierCandidature,
        on_delete=models.CASCADE,
        related_name="demandes_pieces",
    )
    message = models.TextField(blank=True, verbose_name="Message commun au candidat")
    date_limite = models.DateField(null=True, blank=True, verbose_name="À fournir avant le")
    statut = models.CharField(max_length=20, choices=Statut.choices, default=Statut.A_FOURNIR)
    demandee_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="demandes_pieces_creees",
    )
    date_soumission = models.DateTimeField(null=True, blank=True, verbose_name="Déposée le")
    date_decision = models.DateTimeField(null=True, blank=True, verbose_name="Traitée le")

    class Meta:
        verbose_name = "Demande de pièces"
        verbose_name_plural = "Demandes de pièces"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Demande de pièces — {self.dossier.nom_complet} — {self.get_statut_display()}"

    @property
    def est_en_retard(self) -> bool:
        return bool(
            self.date_limite
            and self.statut in (self.Statut.A_FOURNIR, self.Statut.A_CORRIGER)
            and timezone.localdate() > self.date_limite
        )

    @property
    def est_a_verifier(self) -> bool:
        return self.statut == self.Statut.A_VERIFIER

    def marquer_deposee(self) -> None:
        self.statut = self.Statut.A_VERIFIER
        self.date_soumission = timezone.now()
        self.date_decision = None
        self.save(update_fields=["statut", "date_soumission", "date_decision", "updated_at"])

    def marquer_decision(self, *, comporte_refus: bool) -> None:
        self.statut = self.Statut.A_CORRIGER if comporte_refus else self.Statut.VALIDEE
        self.date_decision = timezone.now()
        self.save(update_fields=["statut", "date_decision", "updated_at"])


class PieceDemandee(TimeStampedModel):
    """Pièce appartenant à une demande groupée de justificatifs."""

    class Statut(models.TextChoices):
        DEMANDEE = "demandee", "Demandée"
        DEPOSEE = "deposee", "Déposée — à vérifier"
        VALIDEE = "validee", "Validée"
        REFUSEE = "refusee", "Refusée — à refournir"

    dossier = models.ForeignKey(
        DossierCandidature,
        on_delete=models.CASCADE,
        related_name="pieces_demandees",
    )
    demande = models.ForeignKey(
        DemandePieces,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="pieces",
    )
    libelle = models.CharField(max_length=150, verbose_name="Pièce demandée")
    precisions = models.TextField(blank=True, verbose_name="Précisions propres à la pièce")
    obligatoire = models.BooleanField(default=True)
    date_limite = models.DateField(null=True, blank=True, verbose_name="À fournir avant le")

    statut = models.CharField(max_length=20, choices=Statut.choices, default=Statut.DEMANDEE)
    fichier = models.FileField(upload_to="candidatures/pieces/%Y/%m/", blank=True, verbose_name="Fichier déposé")

    demandee_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pieces_reclamees",
    )
    date_depot = models.DateTimeField(null=True, blank=True, verbose_name="Déposée le")
    date_decision = models.DateTimeField(null=True, blank=True)
    motif_refus = models.TextField(blank=True, verbose_name="Motif du refus")

    class Meta:
        verbose_name = "Pièce demandée"
        verbose_name_plural = "Pièces demandées"
        ordering = ["statut", "-obligatoire", "libelle"]
        constraints = [
            models.UniqueConstraint(fields=["dossier", "libelle"], name="piece_unique_par_dossier"),
        ]

    def __str__(self):
        return f"{self.libelle} — {self.dossier.prenom} {self.dossier.nom}"

    @property
    def est_fournie(self) -> bool:
        return self.statut in (self.Statut.DEPOSEE, self.Statut.VALIDEE)

    @property
    def est_en_retard(self) -> bool:
        date_limite = self.demande.date_limite if self.demande_id else self.date_limite
        return bool(
            date_limite
            and self.statut in (self.Statut.DEMANDEE, self.Statut.REFUSEE)
            and timezone.localdate() > date_limite
        )

    def deposer(self, fichier) -> None:
        self.fichier = fichier
        self.statut = self.Statut.DEPOSEE
        self.date_depot = timezone.now()
        self.motif_refus = ""
        self.date_decision = None
        self.save(update_fields=["fichier", "statut", "date_depot", "motif_refus", "date_decision", "updated_at"])

    def valider(self) -> None:
        self.statut = self.Statut.VALIDEE
        self.date_decision = timezone.now()
        self.motif_refus = ""
        self.save(update_fields=["statut", "date_decision", "motif_refus", "updated_at"])

    def refuser(self, motif: str) -> None:
        from django.core.exceptions import ValidationError

        if not motif.strip():
            raise ValidationError("Indiquez au candidat ce qui ne convient pas.")
        self.statut = self.Statut.REFUSEE
        self.motif_refus = motif.strip()
        self.date_decision = timezone.now()
        self.save(update_fields=["statut", "motif_refus", "date_decision", "updated_at"])
