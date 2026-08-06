"""Domaine commercial : livres, commandes, stock et alertes."""

import uuid
from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.urls import reverse
from django.utils import timezone

from apps.core.models import TimeStampedModel, UUIDModel


class DestinationLivraison(models.TextChoices):
    GUYANE = "Guyane", "Guyane"
    GUADELOUPE = "Guadeloupe", "Guadeloupe"
    MARTINIQUE = "Martinique", "Martinique"


class TypeLivraison(models.TextChoices):
    STANDARD = "standard", "Standard"
    EXPRESS = "express", "Express"
    RETRAIT_SUR_PLACE = "retrait_sur_place", "Retrait à l'institut"


class ProduitLivre(UUIDModel, TimeStampedModel):
    """Livre proposé à la vente, distinct de la notice de bibliothèque."""

    notice = models.OneToOneField(
        "library.NoticeBibliographique",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="produit_boutique",
        help_text="Notice documentaire correspondante, lorsqu'elle existe.",
    )
    titre = models.CharField(max_length=300)
    slug = models.SlugField(max_length=300, unique=True)
    sku = models.CharField(max_length=60, unique=True, verbose_name="Référence / SKU")
    isbn = models.CharField(max_length=20, blank=True, verbose_name="ISBN")
    auteur = models.CharField(max_length=300, blank=True)
    description = models.TextField(blank=True)
    prix_ttc = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
        verbose_name="Prix TTC",
    )
    image = models.ImageField(upload_to="commerce/livres/", blank=True)
    poids_grammes = models.PositiveIntegerField(
        default=1,
        validators=[MinValueValidator(1)],
        verbose_name="Poids (g)",
    )
    stock_physique = models.PositiveIntegerField(default=0)
    stock_reserve = models.PositiveIntegerField(default=0, editable=False, verbose_name="Stock réservé")
    seuil_alerte = models.PositiveIntegerField(default=2, verbose_name="Seuil d'alerte")
    actif = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Livre en vente"
        verbose_name_plural = "Livres en vente"
        ordering = ["titre"]
        constraints = [
            models.CheckConstraint(condition=models.Q(prix_ttc__gte=0), name="commerce_prix_livre_positif"),
            models.CheckConstraint(
                condition=models.Q(stock_reserve__lte=models.F("stock_physique")),
                name="commerce_stock_reserve_borne",
            ),
            models.CheckConstraint(condition=models.Q(poids_grammes__gte=1), name="commerce_poids_livre_positif"),
        ]
        indexes = [
            models.Index(fields=["actif", "titre"]),
            models.Index(fields=["sku"]),
            models.Index(fields=["isbn"]),
        ]

    def __str__(self):
        return f"{self.titre} ({self.sku})"

    def get_absolute_url(self):
        return reverse("commerce:produit_detail", kwargs={"slug": self.slug})

    @property
    def stock_disponible(self) -> int:
        return max(self.stock_physique - self.stock_reserve, 0)

    @property
    def en_alerte_stock(self) -> bool:
        return self.stock_disponible <= self.seuil_alerte


class TarifLivraison(TimeStampedModel):
    """Montant contractuel d'une livraison pour une destination, un mode et un poids."""

    destination = models.CharField(max_length=20, choices=DestinationLivraison.choices)
    type_livraison = models.CharField(max_length=20, choices=TypeLivraison.choices)
    poids_max_grammes = models.PositiveIntegerField(
        validators=[MinValueValidator(1)],
        verbose_name="Poids maximal (g)",
    )
    prix_ttc = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
        verbose_name="Prix TTC",
    )
    transporteur = models.CharField(max_length=80, blank=True)
    offre = models.CharField(max_length=120, blank=True)
    source_url = models.URLField(max_length=500, blank=True, verbose_name="Source officielle")
    date_effet = models.DateField(null=True, blank=True, verbose_name="Date d'effet")
    actif = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Tarif de livraison"
        verbose_name_plural = "Tarifs de livraison"
        ordering = ["destination", "type_livraison", "poids_max_grammes"]
        constraints = [
            models.UniqueConstraint(
                fields=["destination", "type_livraison", "poids_max_grammes"],
                name="commerce_tarif_livraison_unique",
            ),
            models.CheckConstraint(
                condition=models.Q(poids_max_grammes__gte=1),
                name="commerce_tarif_poids_positif",
            ),
            models.CheckConstraint(condition=models.Q(prix_ttc__gt=0), name="commerce_tarif_prix_positif"),
        ]
        indexes = [
            models.Index(fields=["destination", "type_livraison", "actif", "poids_max_grammes"]),
        ]

    def __str__(self):
        return (
            f"{self.get_destination_display()} — {self.get_type_livraison_display()} — "
            f"jusqu'à {self.poids_max_grammes} g : {self.prix_ttc} €"
        )


class Commande(UUIDModel, TimeStampedModel):
    """Commande passée depuis le site et suivie par un jeton non devinable."""

    class Statut(models.TextChoices):
        EN_ATTENTE = "en_attente", "En attente de confirmation"
        CONFIRMEE = "confirmee", "Confirmée"
        PREPARATION = "preparation", "En préparation"
        EXPEDIEE = "expediee", "Expédiée"
        LIVREE = "livree", "Livrée"
        ANNULEE = "annulee", "Annulée"

    class StatutPaiement(models.TextChoices):
        EN_ATTENTE = "en_attente", "En attente"
        CONFIRME = "confirme", "Confirmé"
        REMBOURSE = "rembourse", "Remboursé"

    class ModePaiement(models.TextChoices):
        CARTE = "carte", "Carte bancaire"
        VIREMENT = "virement", "Virement bancaire"
        SUR_PLACE = "sur_place", "Paiement auprès du secrétariat"

    numero = models.CharField(max_length=30, unique=True, editable=False)
    jeton_suivi = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    utilisateur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="commandes_boutique",
    )

    prenom = models.CharField(max_length=100)
    nom = models.CharField(max_length=100)
    email = models.EmailField()
    telephone = models.CharField(max_length=30, blank=True)
    adresse = models.CharField(max_length=250)
    complement_adresse = models.CharField(max_length=250, blank=True)
    code_postal = models.CharField(max_length=20)
    ville = models.CharField(max_length=120)
    pays = models.CharField(
        max_length=100,
        choices=DestinationLivraison.choices,
        default=DestinationLivraison.GUADELOUPE,
    )
    commentaire = models.TextField(blank=True)

    statut = models.CharField(max_length=20, choices=Statut.choices, default=Statut.EN_ATTENTE)
    statut_paiement = models.CharField(
        max_length=20,
        choices=StatutPaiement.choices,
        default=StatutPaiement.EN_ATTENTE,
    )
    mode_paiement = models.CharField(max_length=20, choices=ModePaiement.choices, default=ModePaiement.VIREMENT)
    type_livraison = models.CharField(
        max_length=20,
        choices=TypeLivraison.choices,
        default=TypeLivraison.STANDARD,
    )
    poids_total_grammes = models.PositiveIntegerField(default=0, editable=False, verbose_name="Poids total (g)")
    total_produits = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    frais_livraison = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    remise = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        verbose_name="Remise accordée",
        help_text="Montant déduit du total produits (remise étudiant, code promo…).",
    )
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    transporteur = models.CharField(max_length=120, blank=True)
    numero_suivi = models.CharField(max_length=150, blank=True, verbose_name="Numéro de suivi")
    url_suivi_transporteur = models.URLField(blank=True, verbose_name="Lien de suivi transporteur")
    stock_sorti = models.BooleanField(default=False, editable=False)
    date_confirmation = models.DateTimeField(null=True, blank=True)
    date_expedition = models.DateTimeField(null=True, blank=True)
    date_livraison = models.DateTimeField(null=True, blank=True)
    date_annulation = models.DateTimeField(null=True, blank=True)

    class MotifAnnulation(models.TextChoices):
        """Les raisons réelles d'annuler, telles que le secrétariat les rencontre.

        Une liste fermée plutôt qu'un champ libre : c'est ce qui rend les
        annulations comptables. « Rupture de stock » et « Demande du client »
        n'appellent pas la même réaction, et on ne le saura jamais si chacun
        écrit sa propre formule.
        """

        DEMANDE_CLIENT = "demande_client", "Demande du client"
        RUPTURE_STOCK = "rupture_stock", "Rupture de stock"
        PAIEMENT_NON_RECU = "paiement_non_recu", "Paiement jamais reçu"
        ERREUR_SAISIE = "erreur_saisie", "Erreur de saisie ou doublon"
        ADRESSE_INVALIDE = "adresse_invalide", "Adresse de livraison invalide"
        AUTRE = "autre", "Autre motif"

    motif_annulation = models.CharField(
        max_length=30,
        choices=MotifAnnulation.choices,
        blank=True,
        verbose_name="Motif de l'annulation",
    )
    precision_annulation = models.TextField(
        blank=True,
        verbose_name="Précision",
        help_text="Obligatoire lorsque le motif retenu est « Autre motif ».",
    )

    class Meta:
        verbose_name = "Commande"
        verbose_name_plural = "Commandes"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["statut", "-created_at"]),
            models.Index(fields=["email", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.numero} — {self.prenom} {self.nom}"

    def save(self, *args, **kwargs):
        if not self.numero:
            date = timezone.localdate().strftime("%Y%m%d")
            self.numero = f"CMD-{date}-{uuid.uuid4().hex[:8].upper()}"
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("commerce:commande_suivi", kwargs={"jeton": self.jeton_suivi})

    @property
    def nom_complet(self) -> str:
        return f"{self.prenom} {self.nom}".strip()


class LigneCommande(TimeStampedModel):
    """Instantané commercial : le titre et le prix survivent aux changements du catalogue."""

    commande = models.ForeignKey(Commande, on_delete=models.CASCADE, related_name="lignes")
    produit = models.ForeignKey(ProduitLivre, on_delete=models.PROTECT, related_name="lignes_commandes")
    sku = models.CharField(max_length=60)
    titre = models.CharField(max_length=300)
    prix_unitaire = models.DecimalField(max_digits=10, decimal_places=2)
    quantite = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    total_ligne = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        verbose_name = "Ligne de commande"
        verbose_name_plural = "Lignes de commande"
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(condition=models.Q(quantite__gte=1), name="commerce_quantite_commande_positive")
        ]

    def __str__(self):
        return f"{self.commande.numero} — {self.titre} × {self.quantite}"


class MouvementStock(TimeStampedModel):
    """Journal immuable des variations de stock physique et réservé."""

    class Type(models.TextChoices):
        ENTREE = "entree", "Entrée"
        RESERVATION = "reservation", "Réservation"
        LIBERATION = "liberation", "Libération"
        SORTIE = "sortie", "Sortie"
        AJUSTEMENT = "ajustement", "Ajustement"

    produit = models.ForeignKey(ProduitLivre, on_delete=models.PROTECT, related_name="mouvements_stock")
    type_mouvement = models.CharField(max_length=20, choices=Type.choices)
    variation_physique = models.IntegerField(default=0)
    variation_reserve = models.IntegerField(default=0)
    stock_physique_apres = models.PositiveIntegerField()
    stock_reserve_apres = models.PositiveIntegerField()
    commande = models.ForeignKey(
        Commande,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="mouvements_stock",
    )
    motif = models.CharField(max_length=250, blank=True)
    acteur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="mouvements_stock",
    )

    class Meta:
        verbose_name = "Mouvement de stock"
        verbose_name_plural = "Mouvements de stock"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["produit", "-created_at"])]

    def __str__(self):
        return f"{self.produit.sku} — {self.get_type_mouvement_display()}"


class AlerteStock(TimeStampedModel):
    """Alerte ouverte tant que le stock disponible reste sous son seuil."""

    produit = models.ForeignKey(ProduitLivre, on_delete=models.CASCADE, related_name="alertes_stock")
    stock_disponible_detecte = models.PositiveIntegerField()
    seuil = models.PositiveIntegerField()
    resolue = models.BooleanField(default=False)
    date_resolution = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Alerte de stock"
        verbose_name_plural = "Alertes de stock"
        ordering = ["resolue", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["produit"],
                condition=models.Q(resolue=False),
                name="commerce_une_alerte_stock_ouverte",
            )
        ]

    def __str__(self):
        return f"{self.produit.titre} — {self.stock_disponible_detecte} disponible(s)"
