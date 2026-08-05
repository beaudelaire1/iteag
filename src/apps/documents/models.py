"""Documents de l'institut : ceux qu'on génère, et ceux qu'on rédige.

Deux objets voisins mais distincts, et les confondre serait une erreur :

- « DocumentAdministratif » est **dérivé de données**. L'étudiant demande une
  attestation, la plateforme la fabrique à partir de son dossier. Personne ne
  l'écrit ; personne ne peut en changer le contenu sans changer le dossier.
- « DocumentRedige » est **composé par quelqu'un**. Un courrier, une
  convocation, un compte rendu : le texte n'existe nulle part avant qu'on
  l'écrive, et il engage l'institut sous une référence et une signature.
"""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone

from apps.core.models import TimeStampedModel
from apps.core.services.redaction import en_texte


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


class DocumentRedige(TimeStampedModel):
    """Un document officiel composé par le secrétariat ou la direction.

    Le cycle reprend celui des articles de recherche, que la maison connaît
    déjà : on écrit en brouillon, on finalise, et ce qui est finalisé ne se
    modifie plus en place.

    **La référence n'est attribuée qu'à la finalisation.** Un brouillon
    abandonné ne doit pas consommer un numéro du registre : on chercherait
    ensuite pendant des années le courrier « ITEAG/COU/2026/014 » qui n'a
    jamais existé. Le numéro désigne un document parti, pas une intention.
    """

    class Genre(models.TextChoices):
        COURRIER = "courrier", "Courrier"
        CONVOCATION = "convocation", "Convocation"
        INVITATION = "invitation", "Invitation"
        COMPTE_RENDU = "compte_rendu", "Compte rendu"
        NOTE_SERVICE = "note_service", "Note de service"
        RAPPORT = "rapport", "Rapport"
        ATTESTATION = "attestation", "Attestation"
        AUTRE = "autre", "Autre document"

    # Le préfixe entre dans la référence. Il est court parce qu'il se recopie à
    # la main sur un registre papier et se dicte au téléphone.
    PREFIXES = {
        Genre.COURRIER: "COU",
        Genre.CONVOCATION: "CVN",
        Genre.INVITATION: "INV",
        Genre.COMPTE_RENDU: "CR",
        Genre.NOTE_SERVICE: "NS",
        Genre.RAPPORT: "RAP",
        Genre.ATTESTATION: "ATT",
        Genre.AUTRE: "DOC",
    }

    class Statut(models.TextChoices):
        BROUILLON = "brouillon", "Brouillon"
        FINALISE = "finalise", "Finalisé"

    titre = models.CharField(
        max_length=250,
        verbose_name="Titre interne",
        help_text="Ce qui vous permet de le retrouver dans la liste. Il ne paraît pas sur le document.",
    )
    genre = models.CharField(max_length=20, choices=Genre.choices, default=Genre.COURRIER)
    reference = models.CharField(
        max_length=40,
        blank=True,
        unique=True,
        null=True,
        verbose_name="Référence",
        help_text="Attribuée à la finalisation. Elle ne change plus ensuite.",
    )

    date_document = models.DateField(verbose_name="Date du document", default=timezone.localdate)
    destinataire_nom = models.CharField(max_length=200, blank=True, verbose_name="Destinataire")
    destinataire_adresse = models.TextField(blank=True, verbose_name="Adresse du destinataire")
    objet = models.CharField(max_length=250, verbose_name="Objet")
    corps = models.TextField(blank=True, verbose_name="Corps du document")

    signataire_nom = models.CharField(max_length=150, blank=True, verbose_name="Signataire")
    signataire_qualite = models.CharField(
        max_length=150,
        blank=True,
        verbose_name="Qualité du signataire",
        help_text="Directeur, secrétaire général, responsable de la scolarité…",
    )

    statut = models.CharField(max_length=20, choices=Statut.choices, default=Statut.BROUILLON)
    date_finalisation = models.DateTimeField(null=True, blank=True, verbose_name="Finalisé le")
    fichier_pdf = models.FileField(
        upload_to="documents/rediges/%Y/%m/",
        blank=True,
        verbose_name="PDF finalisé",
    )

    redige_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="documents_rediges",
    )

    class Meta:
        verbose_name = "Document rédigé"
        verbose_name_plural = "Documents rédigés"
        ordering = ["-date_document", "-created_at"]
        indexes = [
            models.Index(fields=["statut", "-date_document"]),
            models.Index(fields=["genre", "-date_document"]),
        ]

    def __str__(self):
        return self.reference or self.titre

    # ── Cycle de vie ──

    @property
    def est_modifiable(self) -> bool:
        """Un document finalisé porte une référence et une signature.

        Le modifier en place changerait ce que désigne un numéro déjà inscrit
        au registre, et peut-être déjà cité dans un courrier reçu.
        """
        return self.statut == self.Statut.BROUILLON

    @property
    def est_finalise(self) -> bool:
        return self.statut == self.Statut.FINALISE

    def _reference_libre(self) -> str:
        """« ITEAG/COU/2026/007 » — séquentiel par genre et par année.

        Le compteur repart à 1 chaque année : c'est ainsi que se tient un
        registre de courrier, et cela rend la référence lisible à l'oral.
        """
        prefixe = self.PREFIXES.get(self.genre, "DOC")
        annee = self.date_document.year
        racine = f"ITEAG/{prefixe}/{annee}/"
        derniere = (
            DocumentRedige.objects.filter(reference__startswith=racine)
            .order_by("-reference")
            .values_list("reference", flat=True)
            .first()
        )
        rang = int(derniere.rsplit("/", 1)[1]) + 1 if derniere else 1
        return f"{racine}{rang:03d}"

    def finaliser(self, *, par=None):
        """Arrête le document : il reçoit sa référence et cesse d'être modifiable.

        L'unicité de la référence est portée par la base, pas par ce calcul :
        deux finalisations simultanées liraient le même dernier numéro, et
        c'est la contrainte qui doit trancher plutôt qu'un doublon silencieux.
        """
        if self.statut != self.Statut.BROUILLON:
            raise ValidationError("Ce document est déjà finalisé.")
        if not self.objet.strip():
            raise ValidationError("Un document finalisé doit porter un objet.")
        if not en_texte(self.corps).strip():
            raise ValidationError("Un document finalisé doit avoir un corps.")

        with transaction.atomic():
            # Conservée si elle existe déjà : un numéro délivré reste délivré,
            # même si le document est repassé par le brouillon entre-temps.
            self.reference = self.reference or self._reference_libre()
            self.statut = self.Statut.FINALISE
            self.date_finalisation = timezone.now()
            if par is not None and self.redige_par_id is None:
                self.redige_par = par
            self.save(update_fields=["reference", "statut", "date_finalisation", "redige_par", "updated_at"])
        return self

    def revenir_en_brouillon(self):
        """Rouvre la rédaction, et jette le PDF qui ne correspond plus.

        La référence, elle, est conservée : un numéro inscrit au registre ne
        se reprend pas. Le PDF, en revanche, décrirait un texte qui n'est plus
        celui du document — le garder serait pire que ne pas en avoir.
        """
        if self.statut != self.Statut.FINALISE:
            raise ValidationError("Seul un document finalisé peut revenir en brouillon.")
        self.statut = self.Statut.BROUILLON
        self.date_finalisation = None
        if self.fichier_pdf:
            self.fichier_pdf.delete(save=False)
        self.save(update_fields=["statut", "date_finalisation", "fichier_pdf", "updated_at"])
        return self
