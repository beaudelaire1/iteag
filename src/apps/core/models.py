import secrets
import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class TimeStampedModel(models.Model):
    """Abstract base model with created/updated timestamps."""

    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class UUIDModel(models.Model):
    """Abstract base model using UUID as primary key."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


# ──────────────────────────────────────────────
# Notifications internes — CDC ETU-009
# ──────────────────────────────────────────────


class Notification(TimeStampedModel):
    """
    Notification interne affichée dans les portails.

    Volontairement sans relation générique : une notification porte une URL de
    destination, pas une référence typée. Cela évite que `core` connaisse les
    modèles des autres applications.
    """

    class Type(models.TextChoices):
        CANDIDATURE = "candidature", "Candidature"
        NOTE_PUBLIEE = "note_publiee", "Note publiée"
        NOUVELLE_RESSOURCE = "nouvelle_ressource", "Nouvelle ressource"
        NOUVEAU_MODULE = "nouveau_module", "Nouveau module"
        ANNONCE = "annonce", "Annonce"
        RAPPEL_SESSION = "rappel_session", "Rappel de session"
        ACCES_OCTROYE = "acces_octroye", "Accès octroyé"
        ATTESTATION = "attestation", "Attestation disponible"
        SYSTEME = "systeme", "Information"

    destinataire = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    type_notification = models.CharField(
        max_length=30,
        choices=Type.choices,
        default=Type.SYSTEME,
        verbose_name="Type",
    )
    titre = models.CharField(max_length=200)
    message = models.TextField(blank=True)
    url_cible = models.CharField(max_length=500, blank=True, verbose_name="Lien")
    lu = models.BooleanField(default=False)
    date_lecture = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Notification"
        verbose_name_plural = "Notifications"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["destinataire", "lu", "-created_at"])]

    def __str__(self):
        return f"{self.titre} → {self.destinataire}"

    def marquer_lue(self):
        if not self.lu:
            self.lu = True
            self.date_lecture = timezone.now()
            self.save(update_fields=["lu", "date_lecture", "updated_at"])


# ──────────────────────────────────────────────
# Journal d'audit — CDC §13
# ──────────────────────────────────────────────


class JournalAudit(TimeStampedModel):
    """
    Trace des actions sensibles : qui, quoi, quand, depuis où.

    L'objet visé est désigné par son libellé et son identifiant, sous forme de
    texte : le journal survit ainsi à la suppression de l'objet, ce qui est
    précisément le cas où l'on a besoin de lui.
    """

    class Action(models.TextChoices):
        CONNEXION = "connexion", "Connexion"
        CONNEXION_ECHEC = "connexion_echec", "Échec de connexion"
        DECONNEXION = "deconnexion", "Déconnexion"
        CREATION = "creation", "Création"
        MODIFICATION = "modification", "Modification"
        SUPPRESSION = "suppression", "Suppression"
        CHANGEMENT_STATUT = "changement_statut", "Changement de statut"
        DEMANDE_ACCES = "demande_acces", "Demande d'accès"
        OCTROI_ACCES = "octroi_acces", "Octroi d'accès"
        REVOCATION_ACCES = "revocation_acces", "Révocation d'accès"
        EXPORT = "export", "Export de données"
        CONSULTATION_SENSIBLE = "consultation_sensible", "Consultation sensible"
        PAIEMENT_RECU = "paiement_recu", "Paiement reçu"
        PAIEMENT_REMBOURSE = "paiement_rembourse", "Paiement remboursé"

    utilisateur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="actions_journalisees",
    )
    action = models.CharField(max_length=30, choices=Action.choices)
    objet_type = models.CharField(max_length=100, blank=True, verbose_name="Type d'objet")
    objet_id = models.CharField(max_length=64, blank=True, verbose_name="Identifiant")
    objet_libelle = models.CharField(max_length=250, blank=True, verbose_name="Libellé")
    adresse_ip = models.GenericIPAddressField(null=True, blank=True, verbose_name="Adresse IP")
    user_agent = models.CharField(max_length=300, blank=True)
    metadonnees = models.JSONField(default=dict, blank=True, verbose_name="Métadonnées")

    class Meta:
        verbose_name = "Entrée du journal d'audit"
        verbose_name_plural = "Journal d'audit"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["-created_at"]),
            models.Index(fields=["utilisateur", "-created_at"]),
            models.Index(fields=["action", "-created_at"]),
        ]

    def __str__(self):
        acteur = self.utilisateur or "anonyme"
        return f"{acteur} — {self.get_action_display()} — {self.objet_libelle or self.objet_type}"


# ──────────────────────────────────────────────
# Newsletter — CDC PUB-012
# ──────────────────────────────────────────────


class AbonneNewsletter(TimeStampedModel):
    """
    Abonné à la lettre d'information, avec double consentement.

    L'inscription ne vaut rien tant que le lien de confirmation n'a pas été
    suivi : c'est ce qui rend la liste conforme et exploitable.
    """

    email = models.EmailField(unique=True)
    confirme = models.BooleanField(default=False, verbose_name="Confirmé")
    date_confirmation = models.DateTimeField(null=True, blank=True)
    actif = models.BooleanField(default=True)
    date_desinscription = models.DateTimeField(null=True, blank=True)
    token_confirmation = models.CharField(max_length=64, unique=True, editable=False)
    token_desinscription = models.CharField(max_length=64, unique=True, editable=False)

    class Meta:
        verbose_name = "Abonné à la newsletter"
        verbose_name_plural = "Abonnés à la newsletter"
        ordering = ["-created_at"]

    def __str__(self):
        etat = "confirmé" if self.confirme else "en attente"
        return f"{self.email} ({etat})"

    def save(self, *args, **kwargs):
        if not self.token_confirmation:
            self.token_confirmation = secrets.token_urlsafe(48)
        if not self.token_desinscription:
            self.token_desinscription = secrets.token_urlsafe(48)
        super().save(*args, **kwargs)

    def confirmer(self):
        if not self.confirme:
            self.confirme = True
            self.actif = True
            self.date_confirmation = timezone.now()
            self.save(update_fields=["confirme", "actif", "date_confirmation", "updated_at"])

    def desinscrire(self):
        if self.actif:
            self.actif = False
            self.date_desinscription = timezone.now()
            self.save(update_fields=["actif", "date_desinscription", "updated_at"])
