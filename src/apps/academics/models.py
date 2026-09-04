from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

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
    # Facultatifs pour permettre la reprise d'un effectif existant : les listes
    # que le secrétariat importe portent des noms, des emails et rarement le
    # rattachement pédagogique exact. Exiger l'un et l'autre à l'import
    # obligeait à renseigner à la main, avant tout dépôt, ce que la fiche sert
    # justement à compléter ensuite.
    parcours = models.ForeignKey(
        "formations.Parcours",
        on_delete=models.PROTECT,
        related_name="etudiants",
        null=True,
        blank=True,
    )
    promotion = models.ForeignKey(
        Promotion,
        on_delete=models.PROTECT,
        related_name="etudiants",
        null=True,
        blank=True,
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
    # L'église d'appartenance était saisie à la candidature puis perdue à
    # l'admission : le secrétariat devait rouvrir le dossier de candidature pour
    # la retrouver. Elle est reprise ici, où vit la scolarité.
    eglise = models.CharField(max_length=200, blank=True, verbose_name="Église d'appartenance")

    class Meta:
        verbose_name = "Profil étudiant"
        verbose_name_plural = "Profils étudiants"

    def __str__(self):
        return f"{self.utilisateur.get_full_name()} — {self.numero_etudiant}"

    @property
    def total_ects_acquis(self):
        """
        Total des crédits acquis.

        L'annotation `ects_acquis_annotes` est utilisée si la vue l'a posée.
        Sans elle, la propriété interroge la base à chaque appel : sur une liste
        de vingt étudiants, cela faisait vingt agrégations — le coût de la page
        croissait avec le nombre de lignes affichées.
        """
        annote = getattr(self, "ects_acquis_annotes", None)
        if annote is not None:
            return annote
        return self.credits_ects.aggregate(total=models.Sum("ects_obtenus"))["total"] or 0

    @property
    def ects_restants(self):
        # Sans parcours, aucun total n'est exigé de cet étudiant : il n'y a donc
        # rien « à valider ». L'état est transitoire — le secrétariat rattache
        # le parcours après la reprise — et zéro se lit là où « None » s'écrirait
        # en toutes lettres dans la fiche.
        if self.parcours_id is None:
            return 0
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

    class Modalite(models.TextChoices):
        PRESENTIEL = "presentiel", "Présentiel"
        DISTANCIEL = "distanciel", "À distance"
        HYBRIDE = "hybride", "Hybride"

    session = models.ForeignKey(SessionAcademique, on_delete=models.CASCADE, related_name="cours_de_session")
    cours = models.ForeignKey("formations.Cours", on_delete=models.PROTECT, related_name="sessions")
    enseignant = models.ForeignKey(
        "formations.Professeur",
        on_delete=models.PROTECT,
        related_name="cours_de_session",
    )
    modalite = models.CharField(max_length=20, choices=Modalite.choices, default=Modalite.PRESENTIEL)
    salle = models.CharField(max_length=100, blank=True)
    horaires = models.TextField(blank=True, verbose_name="Horaires indicatifs")
    statut = models.CharField(max_length=20, choices=StatutCours.choices, default=StatutCours.PROGRAMME)
    capacite = models.PositiveSmallIntegerField(default=30, verbose_name="Capacité")
    inscriptions_ouvertes = models.BooleanField(default=True, verbose_name="Inscriptions ouvertes")
    date_limite_inscription = models.DateField(null=True, blank=True, verbose_name="Date limite d'inscription")
    frais_inscription = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Frais spécifiques",
        help_text="Vide : appliquer le tarif de l'étudiant. Zéro : cours gratuit.",
    )
    informations_pratiques = models.TextField(blank=True)

    # ── Évaluation : date d'examen et fenêtre de dépôt ──
    #
    # Sans fenêtre, un devoir se déposait à n'importe quel moment, y compris
    # après que les notes des autres aient été publiées. L'enseignant n'avait
    # aucun moyen de clore la remise autrement qu'en le demandant.
    date_examen = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Date de l'examen",
        help_text="Annoncée aux étudiants sur la page du cours.",
    )
    depot_ouverture = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Ouverture du dépôt",
        help_text="Avant cette date, aucun devoir ne peut être remis. Vide = ouvert dès maintenant.",
    )
    depot_fermeture = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Fermeture du dépôt",
        help_text="Après cette date, la remise est close. Vide = pas d'échéance.",
    )

    class Meta:
        verbose_name = "Cours de session"
        verbose_name_plural = "Cours de session"
        unique_together = ["session", "cours"]
        ordering = ["session__date_debut", "cours__titre"]
        constraints = [
            models.CheckConstraint(condition=models.Q(capacite__gt=0), name="cours_session_capacite_positive"),
            models.CheckConstraint(
                condition=models.Q(frais_inscription__isnull=True) | models.Q(frais_inscription__gte=0),
                name="cours_session_frais_positifs",
            ),
            # Une fenêtre qui se ferme avant de s'ouvrir n'accepterait jamais
            # rien, sans que l'enseignant comprenne pourquoi.
            models.CheckConstraint(
                condition=models.Q(depot_ouverture__isnull=True)
                | models.Q(depot_fermeture__isnull=True)
                | models.Q(depot_fermeture__gte=models.F("depot_ouverture")),
                name="cours_session_fenetre_depot_coherente",
            ),
        ]

    def __str__(self):
        return f"{self.cours.titre} — {self.session}"

    # ── Fenêtre de dépôt ──────────────────────────────────────

    @property
    def depot_est_ouvert(self) -> bool:
        """La remise des devoirs est-elle possible maintenant ?

        Une borne vide vaut « pas de limite de ce côté » : un enseignant qui ne
        renseigne rien laisse le dépôt ouvert, ce qui est le comportement
        antérieur et donc celui auquel les cours existants s'attendent.
        """
        maintenant = timezone.now()
        if self.depot_ouverture and maintenant < self.depot_ouverture:
            return False
        if self.depot_fermeture and maintenant > self.depot_fermeture:
            return False
        return True

    @property
    def motif_depot_ferme(self) -> str:
        """Pourquoi le dépôt est refusé — vide s'il est ouvert.

        Un refus utile dit à l'étudiant s'il est trop tôt ou trop tard : les
        deux cas appellent des réactions opposées.
        """
        maintenant = timezone.now()
        if self.depot_ouverture and maintenant < self.depot_ouverture:
            return f"La remise ouvrira le {timezone.localtime(self.depot_ouverture):%d/%m/%Y à %H h %M}."
        if self.depot_fermeture and maintenant > self.depot_fermeture:
            return f"La remise est close depuis le {timezone.localtime(self.depot_fermeture):%d/%m/%Y à %H h %M}."
        return ""

    def clean(self):
        super().clean()
        if self.date_limite_inscription and self.date_limite_inscription > self.session.date_fin:
            raise ValidationError(
                {"date_limite_inscription": "La date limite ne peut pas dépasser la fin de la session."}
            )

    @property
    def places_occupees(self):
        nombre_annote = getattr(self, "nombre_inscrits", None)
        return nombre_annote if nombre_annote is not None else self.inscriptions.count()

    @property
    def places_restantes(self):
        return max(self.capacite - self.places_occupees, 0)

    @property
    def est_inscriptible(self):
        aujourd_hui = timezone.localdate()
        return (
            self.inscriptions_ouvertes
            and self.statut == self.StatutCours.PROGRAMME
            and self.session.date_fin >= aujourd_hui
            and (self.date_limite_inscription is None or self.date_limite_inscription >= aujourd_hui)
            and self.places_restantes > 0
        )

    def motif_indisponibilite(self, etudiant=None):
        if not self.inscriptions_ouvertes:
            return "Les inscriptions sont fermées."
        if self.statut != self.StatutCours.PROGRAMME:
            return "Ce cours n'accepte plus de nouvelles inscriptions."
        if self.session.date_fin < timezone.localdate():
            return "Cette session est terminée."
        if self.date_limite_inscription and self.date_limite_inscription < timezone.localdate():
            return "La date limite d'inscription est dépassée."
        if self.places_restantes <= 0:
            return "Ce cours est complet."
        if (
            etudiant
            and self.cours.parcours.exists()
            and not self.cours.parcours.filter(pk=etudiant.parcours_id).exists()
        ):
            return "Ce cours n'est pas ouvert à votre parcours."
        return ""

    def montant_pour(self, etudiant):
        if self.frais_inscription is not None:
            return self.frais_inscription
        if etudiant.formule_tarif_id and etudiant.formule_tarif.actif:
            return etudiant.formule_tarif.montant_session
        return Decimal("0.00")


class InscriptionSession(TimeStampedModel):
    """Inscription d'un étudiant à un cours de session."""

    etudiant = models.ForeignKey(ProfilEtudiant, on_delete=models.CASCADE, related_name="inscriptions")
    cours_session = models.ForeignKey(CoursDeSession, on_delete=models.CASCADE, related_name="inscriptions")
    demande = models.OneToOneField(
        "DemandeInscriptionCours",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="inscription",
    )

    class Meta:
        verbose_name = "Inscription session"
        verbose_name_plural = "Inscriptions session"
        unique_together = ["etudiant", "cours_session"]

    def __str__(self):
        return f"{self.etudiant} → {self.cours_session}"


class DemandeInscriptionCours(TimeStampedModel):
    """Demande étudiante pilotant l'inscription et son contrôle de paiement."""

    class Statut(models.TextChoices):
        SOUMISE = "soumise", "Soumise"
        PAIEMENT_ATTENTE = "paiement_attente", "Paiement à régulariser"
        CONFIRMEE = "confirmee", "Inscription confirmée"
        REFUSEE = "refusee", "Refusée"
        ANNULEE = "annulee", "Annulée par l'étudiant"

    etudiant = models.ForeignKey(ProfilEtudiant, on_delete=models.CASCADE, related_name="demandes_inscription")
    cours_session = models.ForeignKey(
        CoursDeSession,
        on_delete=models.CASCADE,
        related_name="demandes_inscription",
    )
    statut = models.CharField(max_length=25, choices=Statut.choices, default=Statut.SOUMISE)
    montant_du = models.DecimalField(max_digits=8, decimal_places=2, default=0, verbose_name="Montant dû")
    note_etudiant = models.TextField(blank=True, verbose_name="Message de l'étudiant")
    reference_paiement = models.CharField(max_length=120, blank=True, verbose_name="Référence communiquée")
    justificatif_paiement = models.FileField(
        upload_to="paiements/justificatifs/%Y/%m/",
        blank=True,
        verbose_name="Justificatif communiqué",
    )
    paiement = models.ForeignKey(
        "Paiement",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="demandes_inscription",
    )
    exonere_paiement = models.BooleanField(default=False, verbose_name="Exonération de paiement")
    traitee_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="demandes_inscription_traitees",
    )
    date_decision = models.DateTimeField(null=True, blank=True)
    motif_decision = models.TextField(blank=True, verbose_name="Décision / commentaire interne")

    class Meta:
        verbose_name = "Demande d'inscription à un cours"
        verbose_name_plural = "Demandes d'inscription aux cours"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["etudiant", "cours_session"],
                name="demande_unique_etudiant_cours_session",
            ),
            models.CheckConstraint(condition=models.Q(montant_du__gte=0), name="demande_montant_du_positif"),
        ]
        indexes = [
            models.Index(fields=["statut", "-created_at"]),
            models.Index(fields=["etudiant", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.etudiant} → {self.cours_session} ({self.get_statut_display()})"

    @property
    def peut_etre_annulee(self):
        return self.statut in {self.Statut.SOUMISE, self.Statut.PAIEMENT_ATTENTE}


class HistoriqueDemandeInscription(TimeStampedModel):
    """Trace immuable des transitions d'une demande d'inscription."""

    demande = models.ForeignKey(
        DemandeInscriptionCours,
        on_delete=models.CASCADE,
        related_name="historique",
    )
    ancien_statut = models.CharField(max_length=25, choices=DemandeInscriptionCours.Statut.choices, blank=True)
    nouveau_statut = models.CharField(max_length=25, choices=DemandeInscriptionCours.Statut.choices)
    modifie_par = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    commentaire = models.TextField(blank=True)

    class Meta:
        verbose_name = "Historique d'une demande d'inscription"
        verbose_name_plural = "Historique des demandes d'inscription"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.demande_id}: {self.ancien_statut or 'création'} → {self.nouveau_statut}"


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

    # Origine du crédit lorsqu'il ne vient pas d'un cours. Le lien est unique :
    # un stage validé ou une VAE accordée ne peut créditer le dossier qu'une
    # fois, quel que soit le nombre d'enregistrements successifs. Il rend aussi
    # le crédit traçable — on sait quel acte l'a produit.
    stage = models.OneToOneField("Stage", on_delete=models.SET_NULL, null=True, blank=True, related_name="credit")
    vae = models.OneToOneField("VAE", on_delete=models.SET_NULL, null=True, blank=True, related_name="credit")

    class Meta:
        verbose_name = "Crédit ECTS"
        verbose_name_plural = "Crédits ECTS"
        ordering = ["-date_validation"]
        constraints = [
            # Un cours donné, sur une session donnée, ne se valide qu'une fois.
            # La règle est portée par le schéma et pas seulement par le service :
            # une republication, un import ou une saisie manuelle passent tous
            # par ici, et aucun ne doit pouvoir doubler un dossier académique.
            # La condition écarte les crédits externes, dont le cours et la
            # session ne sont pas renseignés.
            models.UniqueConstraint(
                fields=["etudiant", "cours", "session", "source"],
                condition=models.Q(cours__isnull=False, session__isnull=False),
                name="credit_ects_unique_par_cours_et_session",
            )
        ]

    def __str__(self):
        label = self.cours.titre if self.cours else "Crédit externe"
        return f"{self.etudiant} — {label} : {self.ects_obtenus} ECTS ({self.source})"


class Paiement(TimeStampedModel):
    """Suivi des paiements — CDC ADM-003."""

    class ModePaiement(models.TextChoices):
        VIREMENT = "virement", "Virement"
        ESPECES = "especes", "Espèces sur place"

    class StatutPaiement(models.TextChoices):
        EN_ATTENTE = "en_attente", "En attente"
        CONFIRME = "confirme", "Confirmé"
        REMBOURSE = "rembourse", "Remboursé"

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


class PropositionEnseignement(TimeStampedModel):
    """Un cours proposé à un enseignant, qui l'accepte ou le décline.

    Jusqu'ici l'administration désignait l'enseignant d'un cours sans lui
    demander : il le découvrait sur son tableau de bord, parfois la veille, et
    le refus se réglait par téléphone sans laisser de trace. Une proposition
    est donc un objet avec un état — proposée, acceptée, déclinée — et un motif
    quand elle est refusée.

    L'affectation ne bouge qu'à l'acceptation : proposer n'engage rien, et deux
    propositions peuvent coexister sur un même cours tant qu'aucune n'a abouti.
    """

    class Statut(models.TextChoices):
        PROPOSEE = "proposee", "Proposée"
        ACCEPTEE = "acceptee", "Acceptée"
        DECLINEE = "declinee", "Déclinée"

    cours_session = models.ForeignKey(
        "CoursDeSession",
        on_delete=models.CASCADE,
        related_name="propositions",
        verbose_name="Cours de session",
    )
    professeur = models.ForeignKey(
        "formations.Professeur",
        on_delete=models.CASCADE,
        related_name="propositions_enseignement",
    )
    statut = models.CharField(max_length=20, choices=Statut.choices, default=Statut.PROPOSEE)
    message = models.TextField(blank=True, verbose_name="Mot de l'administration")
    motif_refus = models.TextField(blank=True, verbose_name="Motif du refus")
    proposee_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="propositions_envoyees",
    )
    date_reponse = models.DateTimeField(null=True, blank=True, verbose_name="Répondu le")

    class Meta:
        verbose_name = "Proposition d'enseignement"
        verbose_name_plural = "Propositions d'enseignement"
        ordering = ["-created_at"]
        constraints = [
            # Reproposer un cours déjà proposé n'ajoute rien et brouille la
            # file de l'enseignant. Une réponse donnée, en revanche, libère la
            # place : l'administration peut reproposer après un refus.
            models.UniqueConstraint(
                fields=["cours_session", "professeur"],
                condition=models.Q(statut="proposee"),
                name="une_seule_proposition_en_cours",
            ),
        ]
        indexes = [models.Index(fields=["professeur", "statut"])]

    def __str__(self):
        return f"{self.cours_session} → {self.professeur} ({self.get_statut_display()})"

    @property
    def est_en_attente(self) -> bool:
        return self.statut == self.Statut.PROPOSEE

    def accepter(self):
        """L'enseignant prend le cours : c'est ici, et seulement ici, qu'il change de main."""
        if not self.est_en_attente:
            raise ValidationError("Cette proposition a déjà reçu une réponse.")
        self.statut = self.Statut.ACCEPTEE
        self.date_reponse = timezone.now()
        self.save(update_fields=["statut", "date_reponse", "updated_at"])
        self.cours_session.enseignant = self.professeur
        self.cours_session.save(update_fields=["enseignant", "updated_at"])
        return self

    def decliner(self, motif: str):
        """Décliner sans dire pourquoi obligerait l'administration à rappeler."""
        motif = (motif or "").strip()
        if not self.est_en_attente:
            raise ValidationError("Cette proposition a déjà reçu une réponse.")
        if not motif:
            raise ValidationError("Indiquez le motif du refus.")
        self.statut = self.Statut.DECLINEE
        self.motif_refus = motif
        self.date_reponse = timezone.now()
        self.save(update_fields=["statut", "motif_refus", "date_reponse", "updated_at"])
        return self


# Django ne découvre automatiquement que `models.py`. L’import est placé après
# les modèles académiques historiques afin que les relations inverses
# d’assiduité existent avant la construction des requêtes ORM.
from apps.academics.models_assiduite import HistoriquePresence, Presence, SeanceCours  # noqa: E402, F401


class PresenceEtudiant(TimeStampedModel):
    """Bilan d'assiduité d'un étudiant à un cours de session."""

    class Statut(models.TextChoices):
        PRESENT = "present", "Présent"
        RETARD = "retard", "En retard"
        ABSENT_JUSTIFIE = "absent_justifie", "Absent (justifié)"
        ABSENT_NON_JUSTIFIE = "absent_non_justifie", "Absent (non justifié)"

    cours_session = models.ForeignKey(
        CoursDeSession,
        on_delete=models.CASCADE,
        related_name="presences_etudiants",
    )
    etudiant = models.ForeignKey(
        ProfilEtudiant,
        on_delete=models.CASCADE,
        related_name="presences_etudiants",
    )
    statut = models.CharField(
        max_length=20,
        choices=Statut.choices,
        default=Statut.PRESENT,
    )
    commentaire = models.TextField(blank=True, verbose_name="Remarque / justificatif")
    saisi_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="presences_etudiants_saisies",
    )

    class Meta:
        verbose_name = "Présence / Assiduité"
        verbose_name_plural = "Présences / Assiduités"
        ordering = ["etudiant__utilisateur__last_name", "etudiant__utilisateur__first_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["cours_session", "etudiant"],
                name="presence_unique_par_cours_session_etudiant",
            ),
        ]

    def __str__(self):
        return f"{self.etudiant} — {self.cours_session} : {self.get_statut_display()}"
