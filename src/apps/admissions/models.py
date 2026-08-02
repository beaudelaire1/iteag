import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models import TimeStampedModel

# Les pièces réclamées à un candidat sont portées par « PieceDemandee », plus
# bas. Un second modèle, « PieceComplementaire », décrivait le même besoin ;
# les deux ont vécu côte à côte le temps d'une fusion de branches, sans que
# l'interface n'en connaisse jamais qu'un. Le doublon a été retiré.


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


class PieceDemandee(TimeStampedModel):
    """
    Pièce réclamée à un candidat, une fois son dossier tranché.

    Le formulaire public ne recueille que trois pièces génériques — identité,
    diplômes, « autre document ». Cela suffit pour instruire une candidature ;
    cela ne suffit pas pour constituer un dossier d'inscription, qui demande des
    justificatifs que l'on ne connaît qu'après avoir statué, et qui varient d'un
    parcours et d'un profil à l'autre.

    Sans ce modèle, la seule voie était le champ libre « éléments manquants » :
    le secrétariat écrivait une liste en prose, le candidat renvoyait ses pièces
    par courriel, et plus rien n'était suivi. Une pièce réclamée est ici un
    objet avec un état, une échéance et une trace — donc quelque chose qui se
    relance et se compte.
    """

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
    libelle = models.CharField(max_length=150, verbose_name="Pièce demandée")
    precisions = models.TextField(blank=True, verbose_name="Précisions au candidat")
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
        """La pièce est-elle au dossier ? Une pièce refusée ne l'est plus."""
        return self.statut in (self.Statut.DEPOSEE, self.Statut.VALIDEE)

    @property
    def est_en_retard(self) -> bool:
        return bool(
            self.date_limite
            and self.statut in (self.Statut.DEMANDEE, self.Statut.REFUSEE)
            and timezone.localdate() > self.date_limite
        )

    def deposer(self, fichier) -> None:
        """Enregistre le dépôt du candidat. Un nouveau dépôt efface un refus."""
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
        """Refuse la pièce déposée. Le motif est obligatoire.

        Un refus muet obligerait le candidat à deviner ce qui ne va pas, et le
        secrétariat à réexpliquer par téléphone — ce que ce modèle existe
        précisément pour éviter.
        """
        from django.core.exceptions import ValidationError

        if not motif.strip():
            raise ValidationError("Indiquez au candidat ce qui ne convient pas.")
        self.statut = self.Statut.REFUSEE
        self.motif_refus = motif
        self.date_decision = timezone.now()
        self.save(update_fields=["statut", "motif_refus", "date_decision", "updated_at"])
