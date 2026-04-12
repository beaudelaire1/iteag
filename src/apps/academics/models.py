from django.conf import settings
from django.db import models

from apps.core.models import TimeStampedModel


class Promotion(TimeStampedModel):
    """Cohorte d'étudiants — ex: Promotion 2020-2026."""

    nom = models.CharField(max_length=120, unique=True)
    parcours = models.ForeignKey(
        "formations.Parcours",
        on_delete=models.PROTECT,
        related_name="promotions",
    )
    annee_debut = models.PositiveSmallIntegerField(verbose_name="Année de début")
    annee_fin = models.PositiveSmallIntegerField(verbose_name="Année de fin")
    actif = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Promotion"
        verbose_name_plural = "Promotions"
        ordering = ["-annee_debut"]

    def __str__(self):
        return self.nom


class ProfilEtudiant(TimeStampedModel):
    """
    Profil académique de l'étudiant — CDC section 9.1.
    Un utilisateur avec rôle ETUDIANT possède un ProfilEtudiant.
    """

    class StatutInscription(models.TextChoices):
        PRE_INSCRIT = "pre_inscrit", "Pré-inscrit"
        PAIEMENT_ATTENTE = "paiement_attente", "Paiement en attente"
        INSCRIT = "inscrit", "Inscrit"
        ACTIF = "actif", "Actif"
        SUSPENDU = "suspendu", "Suspendu"
        INACTIF = "inactif", "Inactif"
        DIPLOME = "diplome", "Diplômé"

    utilisateur = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profil_etudiant",
    )
    parcours = models.ForeignKey(
        "formations.Parcours",
        on_delete=models.PROTECT,
        related_name="etudiants",
    )
    promotion = models.ForeignKey(
        Promotion,
        on_delete=models.PROTECT,
        related_name="etudiants",
    )
    numero_etudiant = models.CharField(max_length=20, unique=True, verbose_name="Numéro étudiant")
    statut_inscription = models.CharField(
        max_length=20,
        choices=StatutInscription.choices,
        default=StatutInscription.PRE_INSCRIT,
    )
    formule_tarif = models.ForeignKey(
        "formations.Tarif",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    eglise_fondatrice = models.BooleanField(default=False, verbose_name="Membre d'une église fondatrice")

    class Meta:
        verbose_name = "Profil étudiant"
        verbose_name_plural = "Profils étudiants"

    def __str__(self):
        return f"{self.utilisateur.get_full_name()} — {self.numero_etudiant}"

    @property
    def total_ects_acquis(self):
        return self.credits_ects.aggregate(total=models.Sum("ects_obtenus"))["total"] or 0

    @property
    def ects_restants(self):
        return self.parcours.ects_requis - self.total_ects_acquis


class SessionAcademique(TimeStampedModel):
    """
    Session intensive d'une semaine — CDC section 2.1.
    4 sessions/an : Carnaval, Pâques, Juillet, Toussaint.
    """

    class Periode(models.TextChoices):
        CARNAVAL = "carnaval", "Carnaval"
        PAQUES = "paques", "Pâques"
        JUILLET = "juillet", "Grandes vacances"
        TOUSSAINT = "toussaint", "Toussaint"

    class StatutSession(models.TextChoices):
        PLANIFIEE = "planifiee", "Planifiée"
        EN_COURS = "en_cours", "En cours"
        TERMINEE = "terminee", "Terminée"

    nom = models.CharField(max_length=120)
    periode = models.CharField(max_length=20, choices=Periode.choices)
    annee_academique = models.CharField(max_length=9, help_text="Ex: 2025-2026")
    date_debut = models.DateField(verbose_name="Date de début")
    date_fin = models.DateField(verbose_name="Date de fin")
    statut = models.CharField(max_length=20, choices=StatutSession.choices, default=StatutSession.PLANIFIEE)

    class Meta:
        verbose_name = "Session académique"
        verbose_name_plural = "Sessions académiques"
        ordering = ["-date_debut"]
        unique_together = ["periode", "annee_academique"]

    def __str__(self):
        return f"{self.nom} ({self.annee_academique})"


class CoursDeSession(TimeStampedModel):
    """Cours dispensé lors d'une session — liaison Session × Cours × Enseignant."""

    class StatutCours(models.TextChoices):
        PROGRAMME = "programme", "Programmé"
        EN_COURS = "en_cours", "En cours"
        EVALUATION = "evaluation", "Évaluation"
        TERMINE = "termine", "Terminé"

    session = models.ForeignKey(SessionAcademique, on_delete=models.CASCADE, related_name="cours_de_session")
    cours = models.ForeignKey("formations.Cours", on_delete=models.PROTECT, related_name="sessions")
    enseignant = models.ForeignKey(
        "formations.Professeur",
        on_delete=models.PROTECT,
        related_name="cours_de_session",
    )
    salle = models.CharField(max_length=100, blank=True)
    horaires = models.TextField(blank=True, verbose_name="Horaires indicatifs")
    statut = models.CharField(max_length=20, choices=StatutCours.choices, default=StatutCours.PROGRAMME)

    class Meta:
        verbose_name = "Cours de session"
        verbose_name_plural = "Cours de session"
        unique_together = ["session", "cours"]

    def __str__(self):
        return f"{self.cours.titre} — {self.session}"


class InscriptionSession(TimeStampedModel):
    """Inscription d'un étudiant à un cours de session."""

    etudiant = models.ForeignKey(ProfilEtudiant, on_delete=models.CASCADE, related_name="inscriptions")
    cours_session = models.ForeignKey(CoursDeSession, on_delete=models.CASCADE, related_name="inscriptions")

    class Meta:
        verbose_name = "Inscription session"
        verbose_name_plural = "Inscriptions session"
        unique_together = ["etudiant", "cours_session"]

    def __str__(self):
        return f"{self.etudiant} → {self.cours_session}"


class CreditECTS(TimeStampedModel):
    """
    Crédit ECTS acquis — CDC section 9.1.
    Permet le suivi croisé ITEAG + FLTE.
    """

    class SourceCredit(models.TextChoices):
        ITEAG = "iteag", "ITEAG"
        FLTE = "flte", "FLTE"

    etudiant = models.ForeignKey(ProfilEtudiant, on_delete=models.CASCADE, related_name="credits_ects")
    cours = models.ForeignKey("formations.Cours", on_delete=models.PROTECT, null=True, blank=True)
    session = models.ForeignKey(SessionAcademique, on_delete=models.SET_NULL, null=True, blank=True)
    ects_obtenus = models.DecimalField(max_digits=4, decimal_places=1, default=2.5)
    source = models.CharField(max_length=10, choices=SourceCredit.choices, default=SourceCredit.ITEAG)
    date_validation = models.DateField()

    class Meta:
        verbose_name = "Crédit ECTS"
        verbose_name_plural = "Crédits ECTS"
        ordering = ["-date_validation"]

    def __str__(self):
        label = self.cours.titre if self.cours else "Crédit externe"
        return f"{self.etudiant} — {label} : {self.ects_obtenus} ECTS ({self.source})"


class Paiement(TimeStampedModel):
    """Suivi des paiements — CDC ADM-003."""

    class ModePaiement(models.TextChoices):
        VIREMENT = "virement", "Virement"
        ESPECES = "especes", "Espèces"
        CHEQUE = "cheque", "Chèque"
        AUTRE = "autre", "Autre"

    class StatutPaiement(models.TextChoices):
        EN_ATTENTE = "en_attente", "En attente"
        CONFIRME = "confirme", "Confirmé"

    etudiant = models.ForeignKey(ProfilEtudiant, on_delete=models.CASCADE, related_name="paiements")
    session = models.ForeignKey(SessionAcademique, on_delete=models.SET_NULL, null=True, blank=True)
    montant = models.DecimalField(max_digits=8, decimal_places=2)
    date_paiement = models.DateField()
    mode = models.CharField(max_length=20, choices=ModePaiement.choices)
    statut = models.CharField(max_length=20, choices=StatutPaiement.choices, default=StatutPaiement.EN_ATTENTE)
    reference = models.CharField(max_length=100, blank=True, verbose_name="Référence")
    recu_pdf = models.FileField(upload_to="paiements/recus/", blank=True, verbose_name="Reçu PDF")

    class Meta:
        verbose_name = "Paiement"
        verbose_name_plural = "Paiements"
        ordering = ["-date_paiement"]

    def __str__(self):
        return f"{self.etudiant} — {self.montant} € ({self.get_statut_display()})"


class Stage(TimeStampedModel):
    """Stage obligatoire — CDC section 2.5 / 30 ECTS."""

    class StatutStage(models.TextChoices):
        EN_COURS = "en_cours", "En cours"
        VALIDE = "valide", "Validé"
        NON_VALIDE = "non_valide", "Non validé"

    etudiant = models.ForeignKey(ProfilEtudiant, on_delete=models.CASCADE, related_name="stages")
    type_stage = models.CharField(max_length=200, verbose_name="Type de stage")
    lieu = models.CharField(max_length=200)
    tuteur = models.ForeignKey(
        "formations.Professeur",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stages_tutores",
    )
    date_debut = models.DateField()
    date_fin = models.DateField()
    ects = models.DecimalField(max_digits=4, decimal_places=1, default=30)
    statut = models.CharField(max_length=20, choices=StatutStage.choices, default=StatutStage.EN_COURS)

    class Meta:
        verbose_name = "Stage"
        verbose_name_plural = "Stages"

    def __str__(self):
        return f"{self.etudiant} — {self.type_stage} ({self.get_statut_display()})"


class VAE(TimeStampedModel):
    """Validation des Acquis de l'Expérience — CDC section 2.5."""

    class StatutVAE(models.TextChoices):
        SOUMIS = "soumis", "Soumis"
        EN_EXAMEN = "en_examen", "En examen"
        ACCORDE = "accorde", "Accordé"
        REFUSE = "refuse", "Refusé"

    etudiant = models.ForeignKey(ProfilEtudiant, on_delete=models.CASCADE, related_name="vaes")
    description_experience = models.TextField(verbose_name="Description de l'expérience")
    ects_demandes = models.DecimalField(max_digits=5, decimal_places=1, verbose_name="ECTS demandés")
    ects_accordes = models.DecimalField(max_digits=5, decimal_places=1, default=0, verbose_name="ECTS accordés")
    statut = models.CharField(max_length=20, choices=StatutVAE.choices, default=StatutVAE.SOUMIS)
    date_soumission = models.DateField(auto_now_add=True)
    date_decision = models.DateField(null=True, blank=True)

    class Meta:
        verbose_name = "VAE"
        verbose_name_plural = "VAE"

    def __str__(self):
        return f"{self.etudiant} — VAE {self.ects_demandes} ECTS ({self.get_statut_display()})"
