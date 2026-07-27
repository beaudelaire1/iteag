"""
Règlements en ligne — la couche de paiement commune aux trois usages.

Trois choses se paient à l'ITEAG, et elles n'ont rien à voir entre elles : un
module de formation (immatériel, accès perpétuel), des frais d'inscription
(administratifs, rattachés à un dossier étudiant), un livre (physique, avec
stock et expédition). Les faire entrer dans un même modèle métier abîmerait
les invariants de chacun — la boutique tient un stock qu'une formation n'a pas.

Ce qu'ils partagent n'est pas le métier, c'est **l'encaissement** : un montant,
une TVA, une session Stripe, un état, et une contrepartie à délivrer une fois
l'argent reçu. C'est cela, et seulement cela, que porte cette application.

`Reglement` désigne sa contrepartie par une clé étrangère par nature, et une
contrainte de base garantit qu'il y en a exactement une. Une relation générique
aurait évité la migration à chaque nouvelle nature, au prix de l'intégrité
référentielle — mauvais échange quand il s'agit d'argent.
"""

from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.urls import reverse

from apps.core.models import TimeStampedModel, UUIDModel

CENTIMES = Decimal("0.01")


class Reglement(UUIDModel, TimeStampedModel):
    """Un encaissement, son objet, et la contrepartie qu'il ouvre."""

    class Nature(models.TextChoices):
        MODULE = "module", "Module de formation"
        FRAIS_INSCRIPTION = "frais_inscription", "Frais d'inscription"
        COMMANDE = "commande", "Commande de la boutique"

    class Statut(models.TextChoices):
        # Un règlement naît en attente : la session Stripe existe, l'argent non.
        EN_ATTENTE = "en_attente", "En attente de paiement"
        PAYE = "paye", "Payé"
        ECHOUE = "echoue", "Échoué"
        ABANDONNE = "abandonne", "Abandonné"
        REMBOURSE = "rembourse", "Remboursé"
        LITIGE = "litige", "Contesté"

    nature = models.CharField(max_length=30, choices=Nature.choices)

    # ── La contrepartie : exactement une des trois ──
    module = models.ForeignKey(
        "elearning.ModuleFormation",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="reglements",
    )
    commande = models.ForeignKey(
        "commerce.Commande",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="reglements",
    )
    etudiant = models.ForeignKey(
        "academics.ProfilEtudiant",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="reglements",
        help_text="Dossier crédité — obligatoire pour un module ou des frais d'inscription.",
    )

    # ── Le payeur ──
    utilisateur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reglements",
    )
    email = models.EmailField(help_text="Adresse à laquelle le reçu Stripe est envoyé.")
    libelle = models.CharField(max_length=250, help_text="Ce que le payeur lit sur sa page de paiement.")

    # ── Les montants ──
    #
    # Le TTC est la référence : c'est le prix affiché, et c'est ce que Stripe
    # encaisse. La TVA est saisie au formulaire, pas calculée par un service
    # externe — l'ITEAG peut relever de l'exonération de la formation
    # professionnelle sur ses modules tout en la facturant sur ses livres.
    # HT et TVA sont dérivés puis figés : un taux qui change plus tard ne doit
    # pas réécrire l'histoire comptable.
    montant_ttc = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
        verbose_name="Montant TTC",
    )
    taux_tva = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
        verbose_name="Taux de TVA (%)",
    )
    montant_ht = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Montant HT")
    montant_tva = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Dont TVA")
    devise = models.CharField(max_length=3, default="EUR")

    statut = models.CharField(max_length=20, choices=Statut.choices, default=Statut.EN_ATTENTE)

    # ── Les références Stripe ──
    #
    # `session_stripe` est unique : c'est la clé de rapprochement lorsqu'une
    # notification arrive, et l'unicité empêche deux règlements de se disputer
    # le même encaissement.
    session_stripe = models.CharField(max_length=255, blank=True, db_index=True, verbose_name="Session Stripe")
    intention_stripe = models.CharField(max_length=255, blank=True, verbose_name="PaymentIntent Stripe")

    date_paiement = models.DateTimeField(null=True, blank=True)
    date_remboursement = models.DateTimeField(null=True, blank=True)
    motif_echec = models.TextField(blank=True)
    # La contrepartie n'est délivrée qu'une fois. Ce drapeau la garde, en plus
    # de l'idempotence des services appelés : deux filets valent mieux qu'un
    # quand Stripe redélivre une notification.
    contrepartie_delivree = models.BooleanField(default=False, editable=False)

    class Meta:
        verbose_name = "Règlement"
        verbose_name_plural = "Règlements"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["session_stripe"],
                condition=~models.Q(session_stripe=""),
                name="paiements_session_stripe_unique",
            ),
            models.CheckConstraint(
                condition=models.Q(montant_ttc__gt=0),
                name="paiements_montant_positif",
            ),
            models.CheckConstraint(
                condition=models.Q(taux_tva__gte=0) & models.Q(taux_tva__lte=100),
                name="paiements_taux_tva_valide",
            ),
            # Exactement une contrepartie, cohérente avec la nature déclarée.
            models.CheckConstraint(
                condition=(
                    models.Q(nature="module", module__isnull=False, commande__isnull=True)
                    | models.Q(nature="frais_inscription", module__isnull=True, commande__isnull=True)
                    | models.Q(nature="commande", commande__isnull=False, module__isnull=True)
                ),
                name="paiements_contrepartie_coherente",
            ),
        ]
        indexes = [
            models.Index(fields=["statut", "-created_at"]),
            models.Index(fields=["nature", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.libelle} — {self.montant_ttc} {self.devise} ({self.get_statut_display()})"

    def get_absolute_url(self):
        return reverse("paiements:recu", kwargs={"pk": self.pk})

    @staticmethod
    def repartir_tva(montant_ttc: Decimal, taux_tva: Decimal) -> tuple[Decimal, Decimal]:
        """Décompose un TTC en (HT, TVA), arrondi au centime.

        La TVA est calculée par soustraction plutôt que directement : ainsi
        HT + TVA redonne toujours exactement le TTC encaissé, ce qu'un double
        arrondi indépendant ne garantit pas.
        """
        ttc = Decimal(montant_ttc).quantize(CENTIMES, rounding=ROUND_HALF_UP)
        taux = Decimal(taux_tva)
        if taux <= 0:
            return ttc, Decimal("0.00")
        ht = (ttc / (Decimal("1") + taux / Decimal("100"))).quantize(CENTIMES, rounding=ROUND_HALF_UP)
        return ht, ttc - ht

    def save(self, *args, **kwargs):
        self.montant_ht, self.montant_tva = self.repartir_tva(self.montant_ttc, self.taux_tva)
        super().save(*args, **kwargs)

    @property
    def est_paye(self) -> bool:
        return self.statut == self.Statut.PAYE

    @property
    def montant_en_centimes(self) -> int:
        """Stripe raisonne en plus petite unité monétaire, jamais en décimales."""
        return int((self.montant_ttc * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


class EvenementStripe(TimeStampedModel):
    """
    Notification reçue de Stripe, consignée avant d'être suivie d'effet.

    Stripe redélivre : une même notification arrive plusieurs fois, et rien
    n'interdit qu'elle arrive dans le désordre. L'identifiant est donc unique en
    base, et c'est l'insertion elle-même qui décide si l'événement doit être
    traité — pas une lecture préalable, qui laisserait passer deux appels
    concurrents entre le test et l'écriture.
    """

    identifiant = models.CharField(max_length=255, unique=True, verbose_name="Identifiant Stripe")
    type_evenement = models.CharField(max_length=100, verbose_name="Type")
    reglement = models.ForeignKey(
        Reglement,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="evenements",
    )
    charge_utile = models.JSONField(default=dict, verbose_name="Contenu reçu")
    traite = models.BooleanField(default=False)
    erreur = models.TextField(blank=True)

    class Meta:
        verbose_name = "Événement Stripe"
        verbose_name_plural = "Événements Stripe"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["type_evenement", "-created_at"])]

    def __str__(self):
        return f"{self.type_evenement} — {self.identifiant}"
