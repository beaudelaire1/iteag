"""
Domaine de la formation vidéo — voir docs/architecture/uml.md §3.6.

Trois responsabilités sont séparées, et cette séparation est le principal choix
de conception :

* le **contenu**      : ModuleFormation → Chapitre → Lecon → VideoAsset
* le **droit**        : InscriptionModule, RegleAccesParcours
* la **consommation** : ProgressionLecon, JournalAccesVideo, AttestationModule

On peut ainsi changer la politique d'accès sans toucher au contenu, et auditer
la consommation sans polluer le modèle pédagogique.
"""

import secrets

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.urls import reverse
from django.utils import timezone

from apps.core.models import TimeStampedModel, UUIDModel
from apps.elearning.diffusion import (
    CHOIX_FOURNISSEUR,
    PROTECTION_PAR_FOURNISSEUR,
    Lecture,
    NiveauProtection,
    fournisseur_compatible,
)

# ══════════════════════════════════════════════
# Contenu
# ══════════════════════════════════════════════


class ModuleFormation(UUIDModel, TimeStampedModel):
    """Unité de formation vidéo, rattachable à un cours du catalogue."""

    class PolitiqueAcces(models.TextChoices):
        PUBLIC = "public", "Public — accessible à tous"
        AUTHENTIFIE = "authentifie", "Réservé aux comptes connectés"
        INSCRIT_PARCOURS = "inscrit_parcours", "Réservé aux inscrits du parcours"
        SUR_OCTROI = "sur_octroi", "Sur octroi individuel"

    class StatutPublication(models.TextChoices):
        BROUILLON = "brouillon", "Brouillon"
        RELECTURE = "relecture", "En relecture"
        PUBLIE = "publie", "Publié"
        ARCHIVE = "archive", "Archivé"

    class Niveau(models.TextChoices):
        INITIATION = "initiation", "Initiation"
        INTERMEDIAIRE = "intermediaire", "Intermédiaire"
        AVANCE = "avance", "Avancé"

    titre = models.CharField(max_length=250)
    slug = models.SlugField(max_length=250, unique=True)
    code = models.CharField(max_length=20, blank=True, verbose_name="Code module")

    cours = models.ForeignKey(
        "formations.Cours",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="modules_video",
    )
    discipline = models.ForeignKey(
        "formations.Discipline",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="modules_video",
    )
    responsable = models.ForeignKey(
        "formations.Professeur",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="modules_video",
    )
    parcours = models.ManyToManyField(
        "formations.Parcours",
        through="RegleAccesParcours",
        blank=True,
        related_name="modules_video",
    )
    prerequis = models.ManyToManyField(
        "self",
        symmetrical=False,
        blank=True,
        related_name="ouvre_sur",
        verbose_name="Modules prérequis",
    )

    description = models.TextField(blank=True)
    objectifs = models.TextField(blank=True, verbose_name="Objectifs pédagogiques")
    niveau = models.CharField(max_length=20, choices=Niveau.choices, default=Niveau.INITIATION)
    image_couverture = models.ImageField(upload_to="elearning/couvertures/", blank=True)

    duree_totale_secondes = models.PositiveIntegerField(default=0, editable=False, verbose_name="Durée totale")
    ects = models.DecimalField(max_digits=4, decimal_places=1, default=0, verbose_name="ECTS")

    politique_acces = models.CharField(
        max_length=20,
        choices=PolitiqueAcces.choices,
        default=PolitiqueAcces.INSCRIT_PARCOURS,
        verbose_name="Politique d'accès",
    )
    statut = models.CharField(max_length=20, choices=StatutPublication.choices, default=StatutPublication.BROUILLON)
    certifiant = models.BooleanField(default=False, help_text="Délivre une attestation à la complétion")
    autorise_revision = models.BooleanField(
        default=True,
        verbose_name="Relecture après complétion",
        help_text="L'étudiant peut revoir le module une fois terminé",
    )
    seuil_completion = models.PositiveSmallIntegerField(
        default=80,
        validators=[MinValueValidator(50), MaxValueValidator(100)],
        verbose_name="Seuil de complétion (%)",
    )
    date_publication = models.DateTimeField(null=True, blank=True)
    ordre = models.PositiveSmallIntegerField(default=0)

    class Meta:
        verbose_name = "Module de formation"
        verbose_name_plural = "Modules de formation"
        ordering = ["ordre", "titre"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(seuil_completion__gte=50, seuil_completion__lte=100),
                name="module_seuil_completion_valide",
            )
        ]

    def __str__(self):
        return self.titre

    def get_absolute_url(self):
        return reverse("elearning:module_detail", kwargs={"slug": self.slug})

    @property
    def est_publie(self) -> bool:
        return self.statut == self.StatutPublication.PUBLIE

    @property
    def duree_minutes(self) -> int:
        return round(self.duree_totale_secondes / 60)

    def lecons(self):
        """Toutes les leçons du module, dans l'ordre de lecture."""
        return Lecon.objects.filter(chapitre__module=self).select_related("chapitre", "video")

    def recalculer_duree(self) -> int:
        total = self.lecons().aggregate(total=models.Sum("duree_secondes"))["total"] or 0
        if total != self.duree_totale_secondes:
            ModuleFormation.objects.filter(pk=self.pk).update(duree_totale_secondes=total)
            self.duree_totale_secondes = total
        return total

    def clean(self):
        super().clean()
        if self.pk and self._cycle_de_prerequis():
            raise ValidationError({"prerequis": "Les prérequis forment un cycle : le module se précède lui-même."})

    def _cycle_de_prerequis(self) -> bool:
        """Un module ne peut pas dépendre de lui-même, même indirectement."""
        vus, a_visiter = set(), list(self.prerequis.all())
        while a_visiter:
            module = a_visiter.pop()
            if module.pk == self.pk:
                return True
            if module.pk in vus:
                continue
            vus.add(module.pk)
            a_visiter.extend(module.prerequis.all())
        return False

    @property
    def acces_est_restreint(self) -> bool:
        """La politique de ce module promet-elle une restriction ?"""
        return self.politique_acces != self.PolitiqueAcces.PUBLIC

    def apercus_couvrent_tout(self) -> bool:
        """Toutes les leçons sont-elles en aperçu gratuit ?

        Un aperçu contourne le contrôle d'accès par construction : c'est sa
        raison d'être. Mais si *toutes* les leçons le sont, la politique du
        module ne protège plus rien, et personne ne le voit — ni l'enseignant
        qui coche les cases une à une, ni l'écran d'administration, qui affiche
        toujours « réservé aux inscrits ».
        """
        lecons = list(self.lecons())
        return bool(lecons) and all(lecon.apercu_gratuit for lecon in lecons)

    def peut_etre_publie(self) -> tuple[bool, str]:
        """Un module ne se publie pas si une de ses vidéos n'est pas prête."""
        lecons = list(self.lecons())
        if not lecons:
            return False, "Le module ne contient aucune leçon."
        if self.acces_est_restreint and self.apercus_couvrent_tout():
            return False, (
                f"Toutes les leçons sont en aperçu gratuit : « {self.get_politique_acces_display()} » "
                "ne protégerait rien. Retirez l'aperçu des leçons qui doivent rester réservées, "
                "ou passez le module en accès public si c'est bien l'intention."
            )
        for lecon in lecons:
            if lecon.type_lecon == Lecon.TypeLecon.VIDEO:
                if lecon.video is None:
                    return False, f"La leçon « {lecon.titre} » n'a pas de vidéo."
                if lecon.video.statut_traitement != VideoAsset.StatutTraitement.PRET:
                    return False, f"La vidéo de « {lecon.titre} » est encore en préparation."
                # Dernier filet avant la mise en ligne : la politique d'accès a
                # pu être resserrée après le rattachement de la vidéo. Une leçon
                # d'aperçu y échappe, comme dans la validation de la leçon :
                # son contenu est offert, il n'y a pas d'accès à retirer.
                if not lecon.apercu_gratuit and not fournisseur_compatible(
                    lecon.video.fournisseur, self.politique_acces
                ):
                    return False, (
                        f"La vidéo de « {lecon.titre} » est hébergée chez "
                        f"« {lecon.video.get_fournisseur_display()} », qui ne permet pas de retirer "
                        f"un accès. Incompatible avec « {self.get_politique_acces_display()} »."
                    )
        return True, ""

    def publier(self):
        possible, motif = self.peut_etre_publie()
        if not possible:
            raise ValidationError(motif)
        self.statut = self.StatutPublication.PUBLIE
        self.date_publication = self.date_publication or timezone.now()
        self.save(update_fields=["statut", "date_publication", "updated_at"])


class Chapitre(TimeStampedModel):
    """Regroupement de leçons au sein d'un module."""

    module = models.ForeignKey(ModuleFormation, on_delete=models.CASCADE, related_name="chapitres")
    titre = models.CharField(max_length=250)
    description = models.TextField(blank=True)
    ordre = models.PositiveSmallIntegerField(default=0)

    class Meta:
        verbose_name = "Chapitre"
        verbose_name_plural = "Chapitres"
        ordering = ["ordre", "id"]
        constraints = [models.UniqueConstraint(fields=["module", "ordre"], name="chapitre_ordre_unique_par_module")]

    def __str__(self):
        return f"{self.module.titre} — {self.titre}"


class Lecon(UUIDModel, TimeStampedModel):
    """Unité de consommation : une vidéo, un document, un texte ou un lien."""

    class TypeLecon(models.TextChoices):
        VIDEO = "video", "Vidéo"
        DOCUMENT = "document", "Document"
        TEXTE = "texte", "Texte"
        LIEN_EXTERNE = "lien_externe", "Lien externe"

    chapitre = models.ForeignKey(Chapitre, on_delete=models.CASCADE, related_name="lecons")
    titre = models.CharField(max_length=250)
    slug = models.SlugField(max_length=250)
    type_lecon = models.CharField(max_length=20, choices=TypeLecon.choices, default=TypeLecon.VIDEO)
    ordre = models.PositiveSmallIntegerField(default=0)

    video = models.ForeignKey(
        "VideoAsset",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lecons",
    )
    document = models.FileField(upload_to="elearning/documents/%Y/%m/", blank=True)
    lien_externe = models.URLField(blank=True)
    contenu_texte = models.TextField(blank=True)

    duree_secondes = models.PositiveIntegerField(default=0, verbose_name="Durée")
    apercu_gratuit = models.BooleanField(
        default=False,
        verbose_name="Aperçu gratuit",
        help_text="Accessible sans compte ni droit — vitrine du module",
    )
    obligatoire = models.BooleanField(default=True, help_text="Compte dans le calcul de complétion")

    class Meta:
        verbose_name = "Leçon"
        verbose_name_plural = "Leçons"
        ordering = ["chapitre__ordre", "ordre", "id"]
        constraints = [
            models.UniqueConstraint(fields=["chapitre", "ordre"], name="lecon_ordre_unique_par_chapitre"),
            models.UniqueConstraint(fields=["chapitre", "slug"], name="lecon_slug_unique_par_chapitre"),
        ]

    def __str__(self):
        return self.titre

    @property
    def module(self) -> ModuleFormation:
        return self.chapitre.module

    def clean(self):
        super().clean()
        if self.type_lecon == self.TypeLecon.VIDEO and self.video_id is None:
            raise ValidationError({"video": "Une leçon de type vidéo doit référencer une vidéo externe."})
        if self.type_lecon == self.TypeLecon.LIEN_EXTERNE and not self.lien_externe:
            raise ValidationError({"lien_externe": "Une leçon de type lien doit porter une adresse."})
        self._verifier_protection_video()

    def _verifier_protection_video(self):
        """
        Un fournisseur trop faible ne peut pas servir un module protégé — ADR-005.

        Sans cette règle, coller un identifiant YouTube sur la leçon d'un module
        payant suffirait à percer tout le contrôle d'accès, sans qu'aucune alerte
        ne se déclenche : la page resterait protégée, la vidéo ne le serait plus.

        Une leçon **en aperçu gratuit** y échappe : l'aperçu court-circuite le
        contrôle d'accès par construction — c'est sa raison d'être commerciale.
        Exiger une adresse révocable pour un contenu volontairement offert ne
        protégerait rien, et interdirait le schéma normal d'une vitrine : la
        bande-annonce chez un fournisseur public, les leçons sur adresse signée.
        Décocher l'aperçu fait retomber la leçon sous la règle pleine.
        """
        if self.video_id is None or self.chapitre_id is None or self.apercu_gratuit:
            return
        politique = self.module.politique_acces
        if fournisseur_compatible(self.video.fournisseur, politique):
            return
        raise ValidationError(
            {
                "video": (
                    f"« {self.video.get_fournisseur_display()} » ne protège pas assez pour la politique "
                    f"« {self.module.get_politique_acces_display()} » : l'adresse délivrée ne peut pas être "
                    "retirée une fois partagée. Choisir un fournisseur à adresse signée."
                )
            }
        )

    def save(self, *args, **kwargs):
        if self.video_id and not self.duree_secondes:
            self.duree_secondes = self.video.duree_secondes
        super().save(*args, **kwargs)


class VideoAsset(UUIDModel, TimeStampedModel):
    """
    Fichier vidéo stocké de façon privée — voir ADR-001.

    La clé de stockage est un identifiant opaque : aucune information métier
    n'est déductible d'une adresse interceptée.
    """

    class StatutTraitement(models.TextChoices):
        EN_ATTENTE = "en_attente", "En attente"
        EN_COURS = "en_cours", "En préparation"
        PRET = "pret", "Prêt"
        ERREUR = "erreur", "Erreur"

    titre = models.CharField(max_length=250)
    cle_stockage = models.CharField(
        max_length=500,
        unique=True,
        verbose_name="Clé ou identifiant",
        help_text="Clé de stockage interne, ou identifiant de la vidéo chez le fournisseur externe",
    )
    fournisseur = models.CharField(
        max_length=20,
        default="bunny",
        choices=CHOIX_FOURNISSEUR,
        verbose_name="Fournisseur de diffusion",
    )
    nom_origine = models.CharField(max_length=250, blank=True, verbose_name="Nom du fichier d'origine")

    duree_secondes = models.PositiveIntegerField(default=0, verbose_name="Durée")
    taille_octets = models.BigIntegerField(default=0, verbose_name="Taille")
    checksum_sha256 = models.CharField(max_length=64, blank=True)
    poster = models.ImageField(upload_to="elearning/posters/", blank=True)
    # Fichier déposé depuis la plateforme, gardé le temps de l'envoi chez le
    # fournisseur puis effacé. L'institut convoie la vidéo, il ne l'héberge pas :
    # la conserver ferait payer deux fois le même octet, sans que rien ne la lise
    # jamais depuis ici.
    fichier_source = models.FileField(
        upload_to="elearning/depots/%Y/%m/",
        blank=True,
        verbose_name="Fichier déposé",
        help_text="Effacé dès que le fournisseur a pris la vidéo en charge.",
    )

    statut_traitement = models.CharField(
        max_length=20,
        choices=StatutTraitement.choices,
        default=StatutTraitement.EN_ATTENTE,
        verbose_name="Préparation",
    )
    message_erreur = models.TextField(blank=True)
    cle_hls = models.CharField(max_length=500, blank=True, verbose_name="Manifeste HLS")
    transcription = models.TextField(blank=True, help_text="Améliore l'accessibilité et le référencement")

    uploade_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="videos_deposees",
    )

    class Meta:
        verbose_name = "Vidéo"
        verbose_name_plural = "Vidéos"
        ordering = ["-created_at"]

    def __str__(self):
        return self.titre

    @property
    def est_prete(self) -> bool:
        return self.statut_traitement == self.StatutTraitement.PRET

    @property
    def protection(self) -> str:
        """Ce que le fournisseur de cette vidéo sait garantir."""
        return PROTECTION_PAR_FOURNISSEUR.get(self.fournisseur, NiveauProtection.AUCUNE)

    @property
    def mode_lecture(self) -> str:
        """Comment le gabarit doit rendre cette vidéo : fichier, hls ou iframe."""
        from apps.elearning.diffusion import FOURNISSEURS, BunnyStreamVideo

        return FOURNISSEURS.get(self.fournisseur, BunnyStreamVideo).mode

    def lecture(self, ttl: int = 300, adresse_ip: str = "") -> Lecture:
        """
        Descripteur de lecture éphémère. L'adresse n'est jamais rendue dans un
        gabarit : elle est délivrée à la demande, après revérification du droit.
        """
        from apps.elearning.diffusion import fournisseur as choisir

        return choisir(self.fournisseur).lecture(self.cle_stockage, ttl=ttl, adresse_ip=adresse_ip)

    def url_lecture_signee(self, ttl: int = 300) -> str:
        """Adresse seule — conservée pour les appelants qui n'ont pas besoin du mode."""
        return self.lecture(ttl=ttl).url


class SousTitre(TimeStampedModel):
    """Piste de sous-titres — exigence d'accessibilité WCAG 2.2 AA."""

    video = models.ForeignKey(VideoAsset, on_delete=models.CASCADE, related_name="sous_titres")
    langue = models.CharField(max_length=10, default="fr", help_text="Code BCP 47, par exemple « fr »")
    libelle = models.CharField(max_length=100, default="Français")
    fichier_vtt = models.FileField(upload_to="elearning/sous-titres/", verbose_name="Fichier WebVTT")
    par_defaut = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Sous-titres"
        verbose_name_plural = "Sous-titres"
        constraints = [models.UniqueConstraint(fields=["video", "langue"], name="soustitre_langue_unique_par_video")]

    def __str__(self):
        return f"{self.video.titre} — {self.libelle}"


class RessourceLecon(TimeStampedModel):
    """
    Support pédagogique remis avec une leçon : notes de cours, diaporama,
    bibliographie, lien d'approfondissement…

    Le fichier n'est jamais exposé par son adresse de stockage : il est servi
    par une vue qui revérifie le droit sur la leçon à chaque téléchargement,
    comme la vidéo l'est déjà. Une ressource porte soit un fichier, soit un
    lien externe — jamais les deux, sinon le titre affiché deviendrait ambigu
    sur ce qu'un clic déclenche.
    """

    lecon = models.ForeignKey(Lecon, on_delete=models.CASCADE, related_name="ressources")
    titre = models.CharField(max_length=250)
    fichier = models.FileField(upload_to="elearning/ressources/%Y/%m/", blank=True)
    nom_origine = models.CharField(max_length=250, blank=True, verbose_name="Nom du fichier d'origine")
    lien_externe = models.URLField(blank=True)
    # Figée au dépôt : interroger le stockage à chaque affichage de la leçon
    # coûterait un accès disque par ressource, pour une valeur qui ne change pas.
    taille_octets = models.BigIntegerField(default=0, editable=False, verbose_name="Taille")
    ordre = models.PositiveSmallIntegerField(default=0)
    deposee_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ressources_deposees",
    )

    class Meta:
        verbose_name = "Ressource de leçon"
        verbose_name_plural = "Ressources de leçon"
        ordering = ["ordre", "id"]

    def __str__(self):
        return f"{self.lecon.titre} — {self.titre}"

    def clean(self):
        super().clean()
        if bool(self.fichier) == bool(self.lien_externe):
            raise ValidationError(
                "Une ressource porte soit un fichier, soit un lien externe — exactement l'un des deux."
            )

    def save(self, *args, **kwargs):
        if self.fichier:
            try:
                self.taille_octets = self.fichier.size
            except (OSError, ValueError):
                # Fichier déjà déplacé ou stockage muet : la taille reste celle
                # connue, elle n'est qu'indicative à l'affichage.
                pass
            if not self.nom_origine:
                from pathlib import PurePosixPath

                self.nom_origine = PurePosixPath(self.fichier.name).name[:250]
        super().save(*args, **kwargs)

    @property
    def est_fichier(self) -> bool:
        return bool(self.fichier)

    @property
    def nom_fichier(self) -> str:
        """Nom présenté à l'étudiant — celui du dépôt, pas celui du stockage."""
        from pathlib import PurePosixPath

        if self.nom_origine:
            return self.nom_origine
        return PurePosixPath(self.fichier.name).name if self.fichier else ""

    @property
    def extension(self) -> str:
        from pathlib import PurePosixPath

        return PurePosixPath(self.fichier.name).suffix.lstrip(".").lower() if self.fichier else ""


# ══════════════════════════════════════════════
# Droits
# ══════════════════════════════════════════════


class RegleAccesParcours(TimeStampedModel):
    """Rattachement d'un module à un parcours, avec ses conditions d'octroi."""

    parcours = models.ForeignKey("formations.Parcours", on_delete=models.CASCADE, related_name="regles_modules")
    module = models.ForeignKey(ModuleFormation, on_delete=models.CASCADE, related_name="regles_parcours")
    obligatoire = models.BooleanField(default=True, help_text="Octroyé automatiquement à l'inscription")
    duree_acces_jours = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        verbose_name="Durée d'accès (jours)",
        help_text="Vide = accès sans limite de date",
    )
    ordre_recommande = models.PositiveSmallIntegerField(default=0)

    class Meta:
        verbose_name = "Règle d'accès par parcours"
        verbose_name_plural = "Règles d'accès par parcours"
        ordering = ["ordre_recommande"]
        constraints = [
            models.UniqueConstraint(fields=["parcours", "module"], name="regle_unique_parcours_module"),
        ]

    def __str__(self):
        return f"{self.parcours} → {self.module}"


class InscriptionModule(UUIDModel, TimeStampedModel):
    """
    Droit d'un étudiant sur un module : le droit est une donnée, pas une règle
    codée en dur (ADR-002). Le secrétariat l'administre sans développeur.
    """

    class SourceAcces(models.TextChoices):
        PARCOURS = "parcours", "Parcours"
        SESSION = "session", "Session académique"
        OCTROI_MANUEL = "octroi_manuel", "Octroi manuel"
        LIBRE = "libre", "Accès libre"

    class StatutAcces(models.TextChoices):
        # Un étudiant déjà inscrit à l'institut demande lui-même l'ouverture
        # d'un module : le droit existe alors sans être exerçable. Sans ce
        # statut, la seule voie offerte à l'étudiant était de redéposer une
        # candidature complète, coordonnées comprises.
        DEMANDE = "demande", "Demande en attente"
        ACTIF = "actif", "Actif"
        SUSPENDU = "suspendu", "Suspendu"
        EXPIRE = "expire", "Expiré"
        TERMINE = "termine", "Terminé"
        REVOQUE = "revoque", "Révoqué"

    etudiant = models.ForeignKey(
        "academics.ProfilEtudiant",
        on_delete=models.CASCADE,
        related_name="inscriptions_modules",
    )
    module = models.ForeignKey(ModuleFormation, on_delete=models.CASCADE, related_name="inscriptions")
    source = models.CharField(max_length=20, choices=SourceAcces.choices, default=SourceAcces.PARCOURS)
    statut = models.CharField(max_length=20, choices=StatutAcces.choices, default=StatutAcces.ACTIF)

    date_debut_acces = models.DateField(default=timezone.localdate, verbose_name="Début d'accès")
    date_fin_acces = models.DateField(null=True, blank=True, verbose_name="Fin d'accès")

    progression_percent = models.PositiveSmallIntegerField(
        default=0,
        validators=[MaxValueValidator(100)],
        verbose_name="Progression (%)",
    )
    date_completion = models.DateTimeField(null=True, blank=True)

    octroye_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="acces_octroyes",
    )
    motif_revocation = models.TextField(blank=True)
    # Distingue une suspension propagée depuis le profil étudiant d'une décision
    # prise sur ce module : seule la première se relève automatiquement.
    suspendu_par_propagation = models.BooleanField(default=False, editable=False)

    class Meta:
        verbose_name = "Accès à un module"
        verbose_name_plural = "Accès aux modules"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["etudiant", "module"], name="acces_unique_etudiant_module"),
            models.CheckConstraint(
                condition=models.Q(date_fin_acces__isnull=True)
                | models.Q(date_fin_acces__gte=models.F("date_debut_acces")),
                name="acces_fin_apres_debut",
            ),
            models.CheckConstraint(
                condition=models.Q(progression_percent__lte=100),
                name="acces_progression_max_100",
            ),
        ]

    def __str__(self):
        return f"{self.etudiant} → {self.module} ({self.get_statut_display()})"

    def est_active(self, a_la_date=None) -> bool:
        """Le droit est-il exerçable maintenant ?"""
        jour = a_la_date or timezone.localdate()
        if self.statut == self.StatutAcces.ACTIF:
            pass
        elif self.statut == self.StatutAcces.TERMINE and self.module.autorise_revision:
            pass
        else:
            return False
        if self.date_debut_acces and jour < self.date_debut_acces:
            return False
        if self.date_fin_acces and jour > self.date_fin_acces:
            return False
        return True

    @property
    def est_echue(self) -> bool:
        return bool(self.date_fin_acces and timezone.localdate() > self.date_fin_acces)


# ══════════════════════════════════════════════
# Consommation
# ══════════════════════════════════════════════


class ProgressionLecon(TimeStampedModel):
    """
    Avancement d'un étudiant sur une leçon.

    `temps_visionnage_cumule` est alimenté par des incréments plafonnés côté
    serveur : c'est ce qui empêche de simuler un visionnage pour obtenir une
    attestation.
    """

    inscription = models.ForeignKey(InscriptionModule, on_delete=models.CASCADE, related_name="progressions")
    lecon = models.ForeignKey(Lecon, on_delete=models.CASCADE, related_name="progressions")

    position_secondes = models.PositiveIntegerField(default=0, verbose_name="Reprise à")
    pourcentage_vu = models.PositiveSmallIntegerField(default=0, validators=[MaxValueValidator(100)])
    temps_visionnage_cumule = models.PositiveIntegerField(default=0, verbose_name="Temps réellement visionné")
    termine = models.BooleanField(default=False)

    date_premiere_vue = models.DateTimeField(default=timezone.now)
    date_derniere_vue = models.DateTimeField(default=timezone.now)
    date_completion = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Progression"
        verbose_name_plural = "Progressions"
        ordering = ["-date_derniere_vue"]
        constraints = [
            models.UniqueConstraint(fields=["inscription", "lecon"], name="progression_unique_inscription_lecon"),
            models.CheckConstraint(
                condition=models.Q(pourcentage_vu__lte=100),
                name="progression_pourcentage_max_100",
            ),
        ]

    def __str__(self):
        return f"{self.inscription.etudiant} — {self.lecon} ({self.pourcentage_vu} %)"


class JournalAccesVideo(UUIDModel, TimeStampedModel):
    """
    Trace de chaque demande de lecture, autorisée ou refusée.

    C'est la base de la détection de partage de compte : une même inscription
    consultée depuis de nombreuses adresses en peu de temps se voit.
    """

    class Resultat(models.TextChoices):
        AUTORISE = "autorise", "Autorisé"
        REFUSE_DROIT = "refuse_droit", "Refusé — aucun droit"
        REFUSE_EXPIRE = "refuse_expire", "Refusé — accès expiré"
        REFUSE_QUOTA = "refuse_quota", "Refusé — trop de lectures simultanées"
        REFUSE_PREREQUIS = "refuse_prerequis", "Refusé — prérequis non validés"

    utilisateur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="acces_video",
    )
    video = models.ForeignKey(VideoAsset, on_delete=models.SET_NULL, null=True, blank=True, related_name="acces")
    lecon = models.ForeignKey(Lecon, on_delete=models.SET_NULL, null=True, blank=True, related_name="acces")

    resultat = models.CharField(max_length=20, choices=Resultat.choices)
    adresse_ip = models.GenericIPAddressField(null=True, blank=True, verbose_name="Adresse IP")
    user_agent_hash = models.CharField(max_length=64, blank=True, verbose_name="Empreinte du navigateur")
    ttl_accorde = models.PositiveIntegerField(default=0, verbose_name="Validité accordée (s)")

    class Meta:
        verbose_name = "Accès vidéo"
        verbose_name_plural = "Journal des accès vidéo"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["-created_at"]),
            models.Index(fields=["utilisateur", "-created_at"]),
            models.Index(fields=["resultat", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.utilisateur} — {self.get_resultat_display()} — {self.created_at:%d/%m/%Y %H:%M}"


class AttestationModule(UUIDModel, TimeStampedModel):
    """Attestation de suivi, vérifiable publiquement par son code."""

    inscription = models.OneToOneField(
        InscriptionModule,
        on_delete=models.CASCADE,
        related_name="attestation",
    )
    numero = models.CharField(max_length=40, unique=True, editable=False)
    code_verification = models.CharField(max_length=32, unique=True, editable=False)
    date_emission = models.DateTimeField(default=timezone.now)
    fichier_pdf = models.FileField(upload_to="elearning/attestations/%Y/", blank=True)

    class Meta:
        verbose_name = "Attestation de module"
        verbose_name_plural = "Attestations de module"
        ordering = ["-date_emission"]

    def __str__(self):
        return f"{self.numero} — {self.inscription.etudiant}"

    def save(self, *args, **kwargs):
        if not self.code_verification:
            self.code_verification = secrets.token_urlsafe(18)[:32]
        if not self.numero:
            annee = timezone.now().year
            rang = AttestationModule.objects.filter(numero__startswith=f"ITEAG-MOD-{annee}").count() + 1
            self.numero = f"ITEAG-MOD-{annee}-{rang:05d}"
        super().save(*args, **kwargs)

    def url_verification(self) -> str:
        return reverse("elearning:verifier_attestation", kwargs={"code": self.code_verification})
