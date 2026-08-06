"""Workflows transactionnels des commandes et du stock."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.commerce.models import (
    AlerteStock,
    Commande,
    DestinationLivraison,
    LigneCommande,
    MouvementStock,
    ProduitLivre,
    TarifLivraison,
    TypeLivraison,
)
from apps.core.services.emails import envoyer_email
from apps.core.services.notifications import notifier, notifier_plusieurs


@dataclass(frozen=True)
class DevisLivraison:
    destination: str
    type_livraison: str
    poids_grammes: int
    frais: Decimal
    livraison_offerte: bool
    transporteur: str = ""
    offre: str = ""
    source_url: str = ""
    date_effet: date | None = None

    def total_avec(self, total_produits: Decimal) -> Decimal:
        return Decimal(total_produits) + self.frais


def seuil_livraison_offerte() -> Decimal:
    """Seuil commercial explicite : aucun port gratuit en dessous."""
    return Decimal(str(getattr(settings, "COMMERCE_SEUIL_LIVRAISON_OFFERTE", "150.00")))


def calculer_poids_articles(articles) -> int:
    """Calcule le poids du colis et refuse tout catalogue incomplet."""
    poids_total = 0
    for produit, quantite in articles:
        poids = int(produit.poids_grammes)
        if poids < 1:
            raise ValidationError(f"Le poids de « {produit.titre} » doit être renseigné avant sa vente.")
        poids_total += poids * int(quantite)
    return poids_total


def calculer_devis_livraison(
    *,
    total_produits: Decimal,
    poids_grammes: int,
    destination: str,
    type_livraison: str,
) -> DevisLivraison:
    """Sélectionne le premier palier contractuel couvrant le poids du colis."""
    destinations = {valeur for valeur, _ in DestinationLivraison.choices}
    types = {valeur for valeur, _ in TypeLivraison.choices}

    if type_livraison == TypeLivraison.RETRAIT_SUR_PLACE:
        return DevisLivraison(
            destination=destination or "",
            type_livraison=type_livraison,
            poids_grammes=poids_grammes,
            frais=Decimal("0.00"),
            livraison_offerte=False,
        )

    if destination not in destinations:
        raise ValidationError("Cette destination n'est pas desservie.")
    if type_livraison not in types:
        raise ValidationError("Ce type de livraison n'est pas proposé.")
    if poids_grammes < 1:
        raise ValidationError("Le poids du colis doit être supérieur à zéro.")

    total = Decimal(total_produits)
    seuil = seuil_livraison_offerte()
    if total >= seuil:
        return DevisLivraison(
            destination=destination,
            type_livraison=type_livraison,
            poids_grammes=poids_grammes,
            frais=Decimal("0.00"),
            livraison_offerte=True,
        )

    tarif = (
        TarifLivraison.objects.filter(
            destination=destination,
            type_livraison=type_livraison,
            poids_max_grammes__gte=poids_grammes,
            actif=True,
        )
        .order_by("poids_max_grammes")
        .first()
    )
    if tarif is None:
        libelle_type = TypeLivraison(type_livraison).label.lower()
        raise ValidationError(
            f"Aucun tarif {libelle_type} n'est configuré pour {destination} et un colis de {poids_grammes} g."
        )

    return DevisLivraison(
        destination=destination,
        type_livraison=type_livraison,
        poids_grammes=poids_grammes,
        frais=tarif.prix_ttc,
        livraison_offerte=False,
        transporteur=tarif.transporteur,
        offre=tarif.offre,
        source_url=tarif.source_url,
        date_effet=tarif.date_effet,
    )


def devis_pour_lignes(lignes, *, destination: str, type_livraison: str) -> DevisLivraison:
    articles = [(ligne.produit, ligne.quantite) for ligne in lignes]
    total_produits = sum((ligne.produit.prix_ttc * ligne.quantite for ligne in lignes), Decimal("0.00"))
    return calculer_devis_livraison(
        total_produits=total_produits,
        poids_grammes=calculer_poids_articles(articles),
        destination=destination,
        type_livraison=type_livraison,
    )


def taux_remise_etudiant() -> Decimal:
    """Taux de remise accordé aux étudiants inscrits sur la boutique."""
    return Decimal(str(getattr(settings, "COMMERCE_REMISE_ETUDIANT", "0.10")))


def calculer_remise_etudiant(utilisateur, total_produits: Decimal) -> Decimal:
    """Remise accordée aux étudiants inscrits avec un profil actif.

    Un visiteur anonyme, un enseignant ou un étudiant sans profil de
    scolarité ne reçoit rien : la remise est un avantage lié à l'inscription.
    """
    if not getattr(utilisateur, "is_authenticated", False):
        return Decimal("0.00")
    if utilisateur.role != User.Role.ETUDIANT:
        return Decimal("0.00")
    profil = getattr(utilisateur, "profil_etudiant", None)
    if profil is None:
        return Decimal("0.00")
    taux = taux_remise_etudiant()
    if taux <= 0:
        return Decimal("0.00")
    return (Decimal(total_produits) * taux).quantize(Decimal("0.01"))


def _personnel():
    return User.objects.filter(is_active=True).filter(
        Q(role__in=[User.Role.ADMIN, User.Role.SECRETARIAT]) | Q(is_superuser=True)
    )


def _notifier_alerte_stock(alerte: AlerteStock) -> None:
    produit = alerte.produit
    notifier_plusieurs(
        _personnel(),
        f"Stock minimal — {produit.titre}",
        message=(
            f"Le stock de « {produit.titre} » est descendu au niveau d'alerte. "
            "Pensez au réapprovisionnement : en deçà de zéro, l'ouvrage ne peut plus être commandé."
        ),
        details=[
            {"libelle": "Ouvrage", "valeur": produit.titre},
            {"libelle": "Disponible", "valeur": f"{produit.stock_disponible} exemplaire(s)"},
            {"libelle": "Seuil d'alerte", "valeur": f"{produit.seuil_alerte} exemplaire(s)"},
        ],
        url_cible=reverse("commerce:gestion_stock"),
    )
    destinataire = getattr(settings, "COMMERCE_ALERTE_EMAIL", "")
    if destinataire:
        envoyer_email(
            sujet=f"Stock minimal — {produit.titre}",
            gabarit="commerce/emails/alerte_stock.html",
            contexte={
                "titre": produit.titre,
                "sku": produit.sku,
                "stock_disponible": produit.stock_disponible,
                "seuil": produit.seuil_alerte,
            },
            destinataires=[destinataire],
        )


def synchroniser_alerte_stock(produit: ProduitLivre) -> AlerteStock | None:
    """Ouvre une seule alerte sous le seuil et la résout après réapprovisionnement."""
    if produit.en_alerte_stock:
        alerte, creee = AlerteStock.objects.get_or_create(
            produit=produit,
            resolue=False,
            defaults={
                "stock_disponible_detecte": produit.stock_disponible,
                "seuil": produit.seuil_alerte,
            },
        )
        if not creee and (
            alerte.stock_disponible_detecte != produit.stock_disponible or alerte.seuil != produit.seuil_alerte
        ):
            alerte.stock_disponible_detecte = produit.stock_disponible
            alerte.seuil = produit.seuil_alerte
            alerte.save(update_fields=["stock_disponible_detecte", "seuil", "updated_at"])
        if creee:
            transaction.on_commit(lambda: _notifier_alerte_stock(alerte))
        return alerte

    AlerteStock.objects.filter(produit=produit, resolue=False).update(
        resolue=True,
        date_resolution=timezone.now(),
        updated_at=timezone.now(),
    )
    return None


def _mouvement(
    produit: ProduitLivre,
    type_mouvement: str,
    *,
    variation_physique: int = 0,
    variation_reserve: int = 0,
    commande: Commande | None = None,
    acteur=None,
    motif: str = "",
) -> MouvementStock:
    return MouvementStock.objects.create(
        produit=produit,
        type_mouvement=type_mouvement,
        variation_physique=variation_physique,
        variation_reserve=variation_reserve,
        stock_physique_apres=produit.stock_physique,
        stock_reserve_apres=produit.stock_reserve,
        commande=commande,
        acteur=acteur if getattr(acteur, "is_authenticated", False) else None,
        motif=motif[:250],
    )


def _notification_commande(commande: Commande) -> None:
    notifier_plusieurs(
        _personnel(),
        f"Nouvelle commande {commande.numero}",
        message=(
            f"{commande.nom_complet} a passé une commande dans la boutique. "
            "Elle attend sa préparation dans la gestion des commandes."
        ),
        details=[
            {"libelle": "Commande", "valeur": commande.numero},
            {"libelle": "Client", "valeur": commande.nom_complet},
            {"libelle": "Montant", "valeur": f"{commande.total} €"},
            {"libelle": "Livraison", "valeur": commande.get_pays_display()},
        ],
        url_cible=reverse("commerce:gestion_commandes"),
    )
    suivi_url = f"{getattr(settings, 'SITE_URL', '').rstrip('/')}{commande.get_absolute_url()}"
    envoyer_email(
        sujet=f"Commande {commande.numero} reçue",
        gabarit="commerce/emails/confirmation_commande.html",
        contexte={
            "numero": commande.numero,
            "nom": commande.nom_complet,
            "total": str(commande.total),
            "mode_paiement": commande.get_mode_paiement_display(),
            "suivi_url": suivi_url,
        },
        destinataires=[commande.email],
    )


def _envoyer_statut_commande(commande: Commande, message: str) -> None:
    suivi_url = f"{getattr(settings, 'SITE_URL', '').rstrip('/')}{commande.get_absolute_url()}"
    envoyer_email(
        sujet=f"Commande {commande.numero} — {commande.get_statut_display()}",
        gabarit="commerce/emails/statut_commande.html",
        contexte={
            "numero": commande.numero,
            "nom": commande.nom_complet,
            "statut": commande.get_statut_display(),
            "message": message,
            "transporteur": commande.transporteur,
            "numero_suivi": commande.numero_suivi,
            "url_suivi_transporteur": commande.url_suivi_transporteur,
            "suivi_url": suivi_url,
        },
        destinataires=[commande.email],
    )


@transaction.atomic
def creer_commande(*, donnees: dict, lignes_panier, utilisateur=None) -> Commande:
    """Réserve le stock et crée la commande dans une transaction unique."""
    quantites = {str(ligne.produit.pk): int(ligne.quantite) for ligne in lignes_panier}
    if not quantites:
        raise ValidationError("Votre panier est vide.")

    produits = {
        str(produit.pk): produit
        for produit in ProduitLivre.objects.select_for_update().filter(pk__in=quantites, actif=True).order_by("pk")
    }
    if len(produits) != len(quantites):
        raise ValidationError("Un livre de votre panier n'est plus proposé.")

    total_produits = Decimal("0.00")
    articles = []
    for identifiant, quantite in quantites.items():
        produit = produits[identifiant]
        if quantite < 1 or quantite > produit.stock_disponible:
            raise ValidationError(
                f"Stock insuffisant pour « {produit.titre} » : {produit.stock_disponible} disponible(s)."
            )
        total_produits += produit.prix_ttc * quantite
        articles.append((produit, quantite))

    devis = calculer_devis_livraison(
        total_produits=total_produits,
        poids_grammes=calculer_poids_articles(articles),
        destination=donnees.get("pays", ""),
        type_livraison=donnees.get("type_livraison", ""),
    )

    champs = {
        nom: donnees.get(nom, "")
        for nom in (
            "prenom",
            "nom",
            "email",
            "telephone",
            "adresse",
            "complement_adresse",
            "code_postal",
            "ville",
            "pays",
            "type_livraison",
            "mode_paiement",
            "commentaire",
        )
    }
    commande = Commande.objects.create(
        **champs,
        utilisateur=utilisateur if getattr(utilisateur, "is_authenticated", False) else None,
        poids_total_grammes=devis.poids_grammes,
    )

    for identifiant, quantite in quantites.items():
        produit = produits[identifiant]
        total_ligne = produit.prix_ttc * quantite
        LigneCommande.objects.create(
            commande=commande,
            produit=produit,
            sku=produit.sku,
            titre=produit.titre,
            prix_unitaire=produit.prix_ttc,
            quantite=quantite,
            total_ligne=total_ligne,
        )
        produit.stock_reserve += quantite
        produit.save(update_fields=["stock_reserve", "updated_at"])
        _mouvement(
            produit,
            MouvementStock.Type.RESERVATION,
            variation_reserve=quantite,
            commande=commande,
            acteur=utilisateur,
            motif=f"Réservation pour {commande.numero}",
        )
        synchroniser_alerte_stock(produit)

    commande.total_produits = total_produits
    commande.remise = calculer_remise_etudiant(utilisateur, total_produits)
    commande.frais_livraison = devis.frais
    commande.total = total_produits - commande.remise + devis.frais
    commande.save(update_fields=["total_produits", "remise", "frais_livraison", "total", "updated_at"])
    transaction.on_commit(lambda: _notification_commande(commande))
    return commande


@transaction.atomic
def confirmer_commande(commande: Commande, *, acteur=None) -> Commande:
    commande = Commande.objects.select_for_update().get(pk=commande.pk)
    if commande.statut != Commande.Statut.EN_ATTENTE:
        raise ValidationError("Seule une commande en attente peut être confirmée.")
    commande.statut = Commande.Statut.CONFIRMEE
    commande.statut_paiement = Commande.StatutPaiement.CONFIRME
    commande.date_confirmation = timezone.now()
    commande.save(update_fields=["statut", "statut_paiement", "date_confirmation", "updated_at"])
    if commande.utilisateur:
        notifier(
            commande.utilisateur,
            f"Commande {commande.numero} confirmée",
            message=(
                f"Votre règlement pour la commande {commande.numero} est confirmé. "
                "Elle passe en préparation ; vous serez averti de son expédition."
            ),
            url_cible=commande.get_absolute_url(),
            envoyer_par_email=False,
        )
    transaction.on_commit(
        lambda: _envoyer_statut_commande(
            commande,
            "Votre règlement a été confirmé. Nous préparons maintenant votre commande.",
        )
    )
    return commande


@transaction.atomic
def preparer_commande(commande: Commande) -> Commande:
    commande = Commande.objects.select_for_update().get(pk=commande.pk)
    if commande.statut != Commande.Statut.CONFIRMEE:
        raise ValidationError("La commande doit être confirmée avant sa préparation.")
    commande.statut = Commande.Statut.PREPARATION
    commande.save(update_fields=["statut", "updated_at"])
    return commande


@transaction.atomic
def expedier_commande(
    commande: Commande,
    *,
    acteur=None,
    transporteur: str = "",
    numero_suivi: str = "",
    url_suivi: str = "",
) -> Commande:
    commande = Commande.objects.select_for_update().prefetch_related("lignes").get(pk=commande.pk)
    if commande.statut not in (Commande.Statut.CONFIRMEE, Commande.Statut.PREPARATION):
        raise ValidationError("Cette commande ne peut pas être expédiée dans son état actuel.")

    lignes = list(commande.lignes.all())
    produits = {
        produit.pk: produit
        for produit in ProduitLivre.objects.select_for_update()
        .filter(pk__in=[ligne.produit_id for ligne in lignes])
        .order_by("pk")
    }
    if not commande.stock_sorti:
        for ligne in lignes:
            produit = produits[ligne.produit_id]
            if produit.stock_reserve < ligne.quantite or produit.stock_physique < ligne.quantite:
                raise ValidationError(f"Incohérence de stock sur « {produit.titre} ».")
            produit.stock_physique -= ligne.quantite
            produit.stock_reserve -= ligne.quantite
            produit.save(update_fields=["stock_physique", "stock_reserve", "updated_at"])
            _mouvement(
                produit,
                MouvementStock.Type.SORTIE,
                variation_physique=-ligne.quantite,
                variation_reserve=-ligne.quantite,
                commande=commande,
                acteur=acteur,
                motif=f"Expédition de {commande.numero}",
            )
            synchroniser_alerte_stock(produit)
        commande.stock_sorti = True

    commande.statut = Commande.Statut.EXPEDIEE
    commande.transporteur = transporteur.strip()[:120]
    commande.numero_suivi = numero_suivi.strip()[:150]
    commande.url_suivi_transporteur = url_suivi.strip()
    commande.date_expedition = timezone.now()
    commande.save(
        update_fields=[
            "statut",
            "stock_sorti",
            "transporteur",
            "numero_suivi",
            "url_suivi_transporteur",
            "date_expedition",
            "updated_at",
        ]
    )
    if commande.utilisateur:
        notifier(
            commande.utilisateur,
            f"Commande {commande.numero} expédiée",
            message=(
                f"Votre commande {commande.numero} vient d'être expédiée."
                + (f" Vous pouvez la suivre avec le numéro {commande.numero_suivi}." if commande.numero_suivi else "")
            ),
            url_cible=commande.get_absolute_url(),
            envoyer_par_email=False,
        )
    transaction.on_commit(
        lambda: _envoyer_statut_commande(
            commande,
            "Votre commande a quitté nos locaux."
            + (f" Son numéro de suivi est {commande.numero_suivi}." if commande.numero_suivi else ""),
        )
    )
    return commande


@transaction.atomic
def livrer_commande(commande: Commande) -> Commande:
    commande = Commande.objects.select_for_update().get(pk=commande.pk)
    if commande.statut != Commande.Statut.EXPEDIEE:
        raise ValidationError("Seule une commande expédiée peut être marquée livrée.")
    commande.statut = Commande.Statut.LIVREE
    commande.date_livraison = timezone.now()
    commande.save(update_fields=["statut", "date_livraison", "updated_at"])
    return commande


@transaction.atomic
def annuler_commande(commande: Commande, *, acteur=None, motif: str = "", precision: str = "") -> Commande:
    """Annule une commande, remet le stock en rayon, et dit pourquoi.

    Le motif est retenu dans une liste fermée : c'est ce qui rend les
    annulations comptables. Une rupture de stock et un client qui se ravise
    n'appellent pas la même réaction, et un champ libre ne permet jamais de
    les distinguer après coup.
    """
    commande = Commande.objects.select_for_update().prefetch_related("lignes").get(pk=commande.pk)
    if commande.statut in (Commande.Statut.EXPEDIEE, Commande.Statut.LIVREE):
        raise ValidationError("Une commande déjà expédiée ne peut pas être annulée automatiquement.")
    if commande.statut == Commande.Statut.ANNULEE:
        return commande

    motif = (motif or "").strip()
    precision = (precision or "").strip()
    if motif not in Commande.MotifAnnulation.values:
        raise ValidationError("Choisissez le motif de l'annulation.")
    if motif == Commande.MotifAnnulation.AUTRE and not precision:
        raise ValidationError("« Autre motif » demande une précision : sans elle, l'annulation reste inexpliquée.")

    lignes = list(commande.lignes.all())
    produits = {
        produit.pk: produit
        for produit in ProduitLivre.objects.select_for_update()
        .filter(pk__in=[ligne.produit_id for ligne in lignes])
        .order_by("pk")
    }
    for ligne in lignes:
        produit = produits[ligne.produit_id]
        produit.stock_reserve = max(produit.stock_reserve - ligne.quantite, 0)
        produit.save(update_fields=["stock_reserve", "updated_at"])
        _mouvement(
            produit,
            MouvementStock.Type.LIBERATION,
            variation_reserve=-ligne.quantite,
            commande=commande,
            acteur=acteur,
            motif=f"Annulation de {commande.numero}",
        )
        synchroniser_alerte_stock(produit)

    if commande.statut_paiement == Commande.StatutPaiement.CONFIRME:
        commande.statut_paiement = Commande.StatutPaiement.REMBOURSE
    commande.statut = Commande.Statut.ANNULEE
    commande.date_annulation = timezone.now()
    commande.motif_annulation = motif
    commande.precision_annulation = precision
    commande.save(
        update_fields=[
            "statut",
            "statut_paiement",
            "date_annulation",
            "motif_annulation",
            "precision_annulation",
            "updated_at",
        ]
    )
    libelle = commande.get_motif_annulation_display()
    explication = f"{libelle} — {precision}" if precision else libelle
    transaction.on_commit(
        lambda: _envoyer_statut_commande(
            commande,
            f"Votre commande a été annulée. Motif : {explication}. "
            "Le secrétariat reste disponible si vous avez déjà réglé.",
        )
    )
    return commande


def enregistrer_stock_initial(produit: ProduitLivre, *, acteur=None) -> ProduitLivre:
    """Journalise le stock d'ouverture d'un nouveau livre."""
    if produit.stock_physique:
        _mouvement(
            produit,
            MouvementStock.Type.ENTREE,
            variation_physique=produit.stock_physique,
            acteur=acteur,
            motif="Stock initial",
        )
    synchroniser_alerte_stock(produit)
    return produit


@transaction.atomic
def ajuster_stock(produit: ProduitLivre, variation: int, motif: str, *, acteur=None) -> ProduitLivre:
    produit = ProduitLivre.objects.select_for_update().get(pk=produit.pk)
    nouveau = produit.stock_physique + int(variation)
    if nouveau < 0:
        raise ValidationError("Le stock physique ne peut pas devenir négatif.")
    if nouveau < produit.stock_reserve:
        raise ValidationError(
            f"{produit.stock_reserve} exemplaire(s) sont réservés : impossible de descendre sous ce niveau."
        )
    produit.stock_physique = nouveau
    produit.save(update_fields=["stock_physique", "updated_at"])
    _mouvement(
        produit,
        MouvementStock.Type.ENTREE if variation > 0 else MouvementStock.Type.AJUSTEMENT,
        variation_physique=int(variation),
        acteur=acteur,
        motif=motif,
    )
    synchroniser_alerte_stock(produit)
    return produit
