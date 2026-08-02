from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone

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
    # Une copie se rattache au devoir qui l'a demandée. La clé reste facultative :
    # les évaluations créées avant l'existence des devoirs — stages, VAE, saisies
    # du secrétariat — n'en dépendent pas et continuent de fonctionner.
    devoir = models.ForeignKey(
        "lms.Devoir",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="copies",
    )
    type_evaluation = models.CharField(max_length=20, choices=TypeEvaluation.choices, default=TypeEvaluation.DEVOIR)
    statut = models.CharField(max_length=20, choices=StatutEvaluation.choices, default=StatutEvaluation.EN_ATTENTE)

    # Soumission étudiant
    fichier_soumis = models.FileField(upload_to="lms/devoirs/%Y/%m/", blank=True, verbose_name="Fichier remis")
    date_soumission = models.DateTimeField(null=True, blank=True)
    depot_tardif = models.BooleanField(default=False, verbose_name="Remis en retard")
    # Un délai accordé à un étudiant seul : explicite et daté, plutôt qu'une
    # exception convenue de vive voix dont il ne reste aucune trace.
    date_limite_reportee = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Délai accordé jusqu'au",
    )

    # Notation enseignant
    note = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(20)],
    )
    appreciation = models.TextField(blank=True, verbose_name="Appréciation")
    # La copie annotée rendue à l'étudiant. Une note sans la copie corrigée
    # n'apprend rien : c'est l'annotation qui fait le retour pédagogique, et
    # elle se transmettait jusqu'ici de la main à la main ou par courriel.
    fichier_corrige = models.FileField(
        upload_to="lms/copies-corrigees/%Y/%m/",
        blank=True,
        verbose_name="Copie corrigée",
        help_text="Rendue à l'étudiant en même temps que la note, à la publication.",
    )
    ects_valides = models.DecimalField(
        max_digits=4,
        decimal_places=1,
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(30)],
        verbose_name="ECTS validés",
        help_text="0 ou 2.5",
    )
    date_notation = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Évaluation"
        verbose_name_plural = "Évaluations"
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(note__isnull=True) | Q(note__gte=0, note__lte=20),
                name="evaluation_note_between_0_and_20",
            ),
            models.CheckConstraint(
                condition=Q(ects_valides__gte=0, ects_valides__lte=30),
                name="evaluation_ects_between_0_and_30",
            ),
        ]

    def __str__(self):
        return f"{self.etudiant} — {self.cours_session} ({self.get_statut_display()})"

    @property
    def est_publiee(self) -> bool:
        return self.statut == self.StatutEvaluation.PUBLIE

    @property
    def a_ete_revisee(self) -> bool:
        """Une note publiée puis corrigée doit se voir, y compris par l'étudiant."""
        return self.revisions.exists()

    def echeance(self):
        """Date limite applicable à cet étudiant : le délai accordé prime."""
        if self.date_limite_reportee:
            return self.date_limite_reportee
        return self.devoir.date_fermeture if self.devoir_id else None

    def motif_de_refus_depot(self, a_la_date=None):
        """Pourquoi cet étudiant ne peut pas déposer — vide s'il le peut."""
        maintenant = a_la_date or timezone.now()

        if self.statut not in (self.StatutEvaluation.EN_ATTENTE, self.StatutEvaluation.SOUMIS):
            return "Cette copie est en cours de correction : elle ne peut plus être remplacée."

        if self.date_limite_reportee:
            if maintenant > self.date_limite_reportee:
                echu = timezone.localtime(self.date_limite_reportee)
                return f"Le délai qui vous a été accordé a expiré le {echu:%d/%m/%Y à %H:%M}."
            return ""

        if self.devoir_id is None:
            return ""  # évaluation hors devoir : aucune fenêtre à faire respecter
        return self.devoir.motif_de_refus(maintenant)


class RevisionNote(TimeStampedModel):
    """
    Trace d'une note corrigée après publication — le recours.

    Rien ne permettait de revenir sur une note publiée : ni erreur de saisie, ni
    réclamation d'étudiant, ni seconde lecture. La seule issue passait par la
    base de données, sans que personne ne sache plus tard ce qui avait été
    changé, par qui, ni pourquoi.

    La correction est donc possible, mais jamais muette : le motif est
    obligatoire, l'ancienne note est conservée, et l'étudiant est averti.
    """

    evaluation = models.ForeignKey(Evaluation, on_delete=models.CASCADE, related_name="revisions")
    note_avant = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    note_apres = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    appreciation_avant = models.TextField(blank=True)
    motif = models.TextField(verbose_name="Motif de la révision")
    auteur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="revisions_de_note",
    )

    class Meta:
        verbose_name = "Révision de note"
        verbose_name_plural = "Révisions de note"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["evaluation", "-created_at"])]

    def __str__(self):
        return f"{self.evaluation} : {self.note_avant} → {self.note_apres}"


class Devoir(TimeStampedModel):
    """
    Le travail demandé, distinct des copies qu'il produit.

    Jusqu'ici l'enseignant ne pouvait que « préparer des évaluations » : une
    ligne vide par étudiant, sans consigne, sans date, sans barème. Rien ne
    disait à l'étudiant ce qu'il devait rendre ni pour quand, et rien
    n'empêchait un dépôt trois mois après la session.

    La fenêtre de dépôt vit ici et non sur la copie : une échéance appartient au
    travail demandé, pas à chacun de ceux qui le rendent. Le cas de l'étudiant
    qui obtient un délai reste possible — `Evaluation.date_limite_reportee` le
    porte, et il est alors explicite et traçable au lieu d'être une exception
    silencieuse.
    """

    class Statut(models.TextChoices):
        BROUILLON = "brouillon", "Brouillon"
        PUBLIE = "publie", "Publié aux étudiants"
        CLOS = "clos", "Clos"

    class Modalite(models.TextChoices):
        DEPOT_FICHIER = "depot_fichier", "Dépôt d'un fichier"
        QCM = "qcm", "Questionnaire en ligne"
        PRESENTIEL = "presentiel", "Épreuve en présentiel"

    cours_session = models.ForeignKey(
        "academics.CoursDeSession",
        on_delete=models.CASCADE,
        related_name="devoirs",
    )
    titre = models.CharField(max_length=250)
    consigne = models.TextField(blank=True, verbose_name="Consigne")
    fichier_consigne = models.FileField(
        upload_to="lms/consignes/%Y/%m/",
        blank=True,
        verbose_name="Sujet à télécharger",
    )
    type_evaluation = models.CharField(
        max_length=20,
        choices=Evaluation.TypeEvaluation.choices,
        default=Evaluation.TypeEvaluation.DEVOIR,
    )
    modalite = models.CharField(max_length=20, choices=Modalite.choices, default=Modalite.DEPOT_FICHIER)
    statut = models.CharField(max_length=20, choices=Statut.choices, default=Statut.BROUILLON)

    # ── La fenêtre de dépôt ──
    date_ouverture = models.DateTimeField(
        verbose_name="Ouverture du dépôt",
        help_text="Avant cette date, l'étudiant voit le sujet mais ne peut rien remettre.",
    )
    date_fermeture = models.DateTimeField(
        verbose_name="Fermeture du dépôt",
        help_text="Après cette date, le dépôt est refusé, sauf retard autorisé.",
    )
    retard_accepte = models.BooleanField(
        default=False,
        verbose_name="Accepter les dépôts en retard",
        help_text="Le dépôt reste possible après la fermeture, et il est signalé comme tardif.",
    )

    bareme = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=20,
        validators=[MinValueValidator(1)],
        verbose_name="Barème",
    )
    ects = models.DecimalField(
        max_digits=4,
        decimal_places=1,
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(30)],
        verbose_name="ECTS attribués",
    )

    # ── À qui le devoir s'adresse ──
    # Il ne s'adressait qu'à tout le cours. Un travail de groupe, un rattrapage
    # pour un seul étudiant ou un sujet propre à une promotion devaient donc
    # être donnés hors de la plateforme, et rien n'en était suivi.
    #
    # La cible ne remplace jamais l'inscription : quelle qu'elle soit, seuls
    # les inscrits au cours reçoivent une copie. Désigner une promotion entière
    # n'ouvre pas le devoir à qui n'a pas suivi le cours.

    class Portee(models.TextChoices):
        COURS = "cours", "Tous les inscrits au cours"
        GROUPE = "groupe", "Un groupe de travail"
        PROMOTION = "promotion", "Une promotion"
        ETUDIANTS = "etudiants", "Des étudiants désignés"

    portee = models.CharField(
        max_length=20,
        choices=Portee.choices,
        default=Portee.COURS,
        verbose_name="Destinataires",
    )
    groupe = models.ForeignKey(
        "GroupeEtudiants",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="devoirs",
        verbose_name="Groupe de travail",
    )
    promotion = models.ForeignKey(
        "academics.Promotion",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="devoirs",
    )
    etudiants = models.ManyToManyField(
        "academics.ProfilEtudiant",
        blank=True,
        related_name="devoirs_designes",
        verbose_name="Étudiants désignés",
    )

    class Meta:
        verbose_name = "Devoir"
        verbose_name_plural = "Devoirs"
        ordering = ["-date_fermeture", "-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(date_fermeture__gt=models.F("date_ouverture")),
                name="devoir_fermeture_apres_ouverture",
            ),
        ]
        indexes = [models.Index(fields=["cours_session", "-date_fermeture"])]

    def __str__(self):
        return f"{self.titre} — {self.cours_session}"

    def clean(self):
        super().clean()
        if self.date_ouverture and self.date_fermeture and self.date_fermeture <= self.date_ouverture:
            raise ValidationError({"date_fermeture": "La fermeture doit suivre l'ouverture."})
        if self.portee == self.Portee.GROUPE and self.groupe_id is None:
            raise ValidationError({"groupe": "Désignez le groupe destinataire."})
        if self.portee == self.Portee.PROMOTION and self.promotion_id is None:
            raise ValidationError({"promotion": "Désignez la promotion destinataire."})
        if self.groupe_id and self.groupe.cours_session_id != self.cours_session_id:
            raise ValidationError({"groupe": "Ce groupe appartient à un autre cours."})

    # ── Destinataires ──

    def inscriptions_destinataires(self):
        """Les inscriptions du cours que ce devoir concerne réellement.

        Le filtre part toujours des inscrits : une promotion ou un groupe ne
        peut qu'en restreindre la liste, jamais l'élargir. Sans cela, désigner
        une promotion donnerait le devoir à des étudiants qui ne suivent pas
        le cours — et leur créerait une copie qu'ils n'attendent pas.
        """
        inscriptions = self.cours_session.inscriptions.select_related("etudiant__utilisateur")

        if self.portee == self.Portee.GROUPE and self.groupe_id:
            return inscriptions.filter(etudiant__in=self.groupe.membres.all())
        if self.portee == self.Portee.PROMOTION and self.promotion_id:
            return inscriptions.filter(etudiant__promotion_id=self.promotion_id)
        if self.portee == self.Portee.ETUDIANTS:
            return inscriptions.filter(etudiant__in=self.etudiants.all())
        return inscriptions

    @property
    def libelle_destinataires(self) -> str:
        if self.portee == self.Portee.GROUPE and self.groupe_id:
            return f"Groupe « {self.groupe.nom} »"
        if self.portee == self.Portee.PROMOTION and self.promotion_id:
            return f"Promotion {self.promotion.nom}"
        if self.portee == self.Portee.ETUDIANTS:
            nombre = self.etudiants.count()
            return f"{nombre} étudiant{'s' if nombre > 1 else ''} désigné{'s' if nombre > 1 else ''}"
        return "Tous les inscrits au cours"

    # ── État de la fenêtre ──

    @property
    def est_ouvert(self) -> bool:
        """Le dépôt est-il possible maintenant ?"""
        if self.statut != self.Statut.PUBLIE:
            return False
        maintenant = timezone.now()
        if maintenant < self.date_ouverture:
            return False
        return maintenant <= self.date_fermeture or self.retard_accepte

    @property
    def est_a_venir(self) -> bool:
        return self.statut == self.Statut.PUBLIE and timezone.now() < self.date_ouverture

    @property
    def est_echu(self) -> bool:
        return timezone.now() > self.date_fermeture

    def motif_de_refus(self, a_la_date=None) -> str:
        """Pourquoi ce dépôt est refusé — vide s'il est recevable.

        Un refus utile dit quand rendre, pas seulement que c'est impossible.
        """
        maintenant = a_la_date or timezone.now()
        if self.statut == self.Statut.BROUILLON:
            return "Ce devoir n'est pas encore ouvert par l'enseignant."
        if self.statut == self.Statut.CLOS:
            return "Ce devoir est clos : la correction est terminée."
        if maintenant < self.date_ouverture:
            return f"Le dépôt ouvre le {timezone.localtime(self.date_ouverture):%d/%m/%Y à %H:%M}."
        if maintenant > self.date_fermeture and not self.retard_accepte:
            return f"Le dépôt a fermé le {timezone.localtime(self.date_fermeture):%d/%m/%Y à %H:%M}."
        return ""


class Question(TimeStampedModel):
    """
    Une question d'un questionnaire, et ce qu'elle vaut.

    Le barème est porté par la question et non déduit d'une division du total :
    toutes les questions d'un devoir ne pèsent pas le même poids, et une note
    calculée à partir d'une moyenne arithmétique serait fausse dès la première
    question bonus.
    """

    class TypeQuestion(models.TextChoices):
        CHOIX_UNIQUE = "choix_unique", "Une seule bonne réponse"
        CHOIX_MULTIPLE = "choix_multiple", "Plusieurs bonnes réponses"

    devoir = models.ForeignKey(Devoir, on_delete=models.CASCADE, related_name="questions")
    enonce = models.TextField(verbose_name="Énoncé")
    type_question = models.CharField(
        max_length=20,
        choices=TypeQuestion.choices,
        default=TypeQuestion.CHOIX_UNIQUE,
        verbose_name="Type de question",
    )
    points = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=1,
        validators=[MinValueValidator(Decimal("0.25"))],
        verbose_name="Points",
    )
    explication = models.TextField(
        blank=True,
        verbose_name="Explication",
        help_text="Montrée à l'étudiant après la correction. Une réponse fausse sans explication n'apprend rien.",
    )
    ordre = models.PositiveSmallIntegerField(default=0)

    class Meta:
        verbose_name = "Question"
        verbose_name_plural = "Questions"
        ordering = ["ordre", "id"]

    def __str__(self):
        return self.enonce[:80]

    @property
    def bonnes_reponses(self):
        return self.choix.filter(correct=True)

    def est_valide(self) -> str:
        """Ce qui manque à cette question pour être posée — vide si elle est prête."""
        choix = list(self.choix.all())
        if len(choix) < 2:
            return "Il faut au moins deux propositions."
        correctes = [c for c in choix if c.correct]
        if not correctes:
            return "Aucune proposition n'est marquée comme correcte."
        if self.type_question == self.TypeQuestion.CHOIX_UNIQUE and len(correctes) > 1:
            return "Une question à réponse unique ne peut avoir qu'une seule proposition correcte."
        return ""


class Choix(TimeStampedModel):
    """Une proposition de réponse. Sa justesse n'est jamais envoyée au navigateur."""

    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="choix")
    libelle = models.CharField(max_length=500, verbose_name="Proposition")
    correct = models.BooleanField(default=False, verbose_name="Réponse correcte")
    ordre = models.PositiveSmallIntegerField(default=0)

    class Meta:
        verbose_name = "Proposition"
        verbose_name_plural = "Propositions"
        ordering = ["ordre", "id"]

    def __str__(self):
        return self.libelle[:60]


class ReponseEtudiant(TimeStampedModel):
    """
    Ce qu'un étudiant a coché, conservé tel quel.

    La note se recalcule à partir de ces réponses ; elle n'est pas seule à être
    stockée. Un barème corrigé après coup — une question retirée, une seconde
    bonne réponse admise — peut ainsi être rejoué sur toutes les copies au lieu
    d'être ressaisi à la main.
    """

    evaluation = models.ForeignKey(Evaluation, on_delete=models.CASCADE, related_name="reponses")
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="reponses")
    choix = models.ManyToManyField(Choix, blank=True, related_name="reponses")
    points_obtenus = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    class Meta:
        verbose_name = "Réponse d'étudiant"
        verbose_name_plural = "Réponses d'étudiants"
        ordering = ["question__ordre"]
        constraints = [
            models.UniqueConstraint(fields=["evaluation", "question"], name="reponse_unique_par_question"),
        ]

    def __str__(self):
        return f"{self.evaluation.etudiant} — {self.question}"

    def corriger(self) -> Decimal:
        """Tout ou rien : une réponse partiellement juste ne rapporte pas.

        Le barème partiel a été écarté à dessein — il oblige à décider ce que
        vaut une case oubliée par rapport à une case en trop, et cette décision
        n'appartient pas au code.
        """
        attendus = {choix.pk for choix in self.question.choix.all() if choix.correct}
        donnes = {choix.pk for choix in self.choix.all()}
        self.points_obtenus = self.question.points if donnes == attendus and attendus else Decimal("0")
        return self.points_obtenus


class GroupeEtudiants(TimeStampedModel):
    """
    Un sous-ensemble d'une classe : équipe de projet, groupe de travaux dirigés.

    Rattaché au cours de session et non à la promotion : les groupes d'un cours
    n'ont pas de raison de valoir pour un autre, et un étudiant peut être en
    équipe 1 ici et en équipe 3 ailleurs.
    """

    cours_session = models.ForeignKey(
        "academics.CoursDeSession",
        on_delete=models.CASCADE,
        related_name="groupes",
    )
    nom = models.CharField(max_length=120)
    description = models.TextField(blank=True, help_text="Sujet du projet, consigne propre au groupe…")
    membres = models.ManyToManyField(
        "academics.ProfilEtudiant",
        blank=True,
        related_name="groupes_de_travail",
    )
    couleur = models.CharField(
        max_length=7,
        blank=True,
        help_text="Repère visuel, au format #RRGGBB.",
    )

    class Meta:
        verbose_name = "Groupe d'étudiants"
        verbose_name_plural = "Groupes d'étudiants"
        ordering = ["nom"]
        constraints = [
            models.UniqueConstraint(fields=["cours_session", "nom"], name="groupe_nom_unique_par_cours"),
        ]

    def __str__(self):
        return f"{self.nom} — {self.cours_session}"


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
