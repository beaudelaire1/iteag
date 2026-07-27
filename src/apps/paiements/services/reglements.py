"""
Ouverture d'un règlement — un point d'entrée par nature.

Le prix n'est jamais lu depuis la requête. Il est relu en base au moment de
créer le règlement, et c'est lui que Stripe encaissera : un montant qui
transiterait par le navigateur serait un montant négociable par l'acheteur.
"""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.paiements.models import Reglement


def _payeur(utilisateur, email: str) -> tuple[object | None, str]:
    adresse = email or getattr(utilisateur, "email", "") or ""
    if not adresse:
        raise ValidationError("Une adresse électronique est nécessaire pour envoyer le reçu.")
    return (utilisateur if getattr(utilisateur, "is_authenticated", False) else None), adresse


@transaction.atomic
def pour_module(module, etudiant, *, utilisateur=None, email: str = "") -> Reglement:
    """Règlement d'un module vendu à l'unité.

    Refuse d'ouvrir un second règlement si l'accès est déjà acquis : payer deux
    fois la même formation est une réclamation garantie.
    """
    from apps.elearning.models import InscriptionModule

    if not module.est_vendu:
        raise ValidationError("Ce module n'est pas vendu à l'unité.")
    if not module.est_publie:
        raise ValidationError("Ce module n'est pas encore ouvert à la vente.")
    if etudiant is None:
        raise ValidationError("Un dossier étudiant est nécessaire pour acheter un module.")

    inscription = InscriptionModule.objects.filter(etudiant=etudiant, module=module).first()
    if inscription is not None and inscription.est_active():
        raise ValidationError("Vous avez déjà accès à ce module.")

    en_cours = Reglement.objects.filter(
        module=module,
        etudiant=etudiant,
        statut=Reglement.Statut.EN_ATTENTE,
    ).first()
    if en_cours is not None:
        return en_cours

    porteur, adresse = _payeur(utilisateur, email)
    return Reglement.objects.create(
        nature=Reglement.Nature.MODULE,
        module=module,
        etudiant=etudiant,
        utilisateur=porteur,
        email=adresse,
        libelle=f"Formation — {module.titre}",
        montant_ttc=module.prix_ttc,
        taux_tva=module.taux_tva,
    )


@transaction.atomic
def pour_frais_inscription(
    etudiant,
    *,
    montant_ttc: Decimal,
    taux_tva: Decimal,
    libelle: str = "Frais d'inscription",
    utilisateur=None,
    email: str = "",
) -> Reglement:
    """Règlement de frais administratifs, dont le montant est fixé par le secrétariat."""
    if etudiant is None:
        raise ValidationError("Un dossier étudiant est nécessaire.")
    if Decimal(montant_ttc) <= 0:
        raise ValidationError("Le montant doit être supérieur à zéro.")

    porteur, adresse = _payeur(utilisateur or getattr(etudiant, "utilisateur", None), email)
    return Reglement.objects.create(
        nature=Reglement.Nature.FRAIS_INSCRIPTION,
        etudiant=etudiant,
        utilisateur=porteur,
        email=adresse,
        libelle=libelle,
        montant_ttc=Decimal(montant_ttc),
        taux_tva=Decimal(taux_tva),
    )


@transaction.atomic
def pour_commande(commande, *, taux_tva: Decimal = Decimal("0")) -> Reglement:
    """Règlement d'une commande de la boutique.

    Le total de la commande fait foi, frais de port compris — il a été calculé
    au moment de la commande, à partir du catalogue et non du panier envoyé.
    """
    from apps.commerce.models import Commande

    if commande.statut != Commande.Statut.EN_ATTENTE:
        raise ValidationError("Cette commande n'est plus en attente de règlement.")
    if commande.total <= 0:
        raise ValidationError("Le total de la commande est nul.")

    en_cours = Reglement.objects.filter(commande=commande, statut=Reglement.Statut.EN_ATTENTE).first()
    if en_cours is not None:
        return en_cours

    return Reglement.objects.create(
        nature=Reglement.Nature.COMMANDE,
        commande=commande,
        utilisateur=commande.utilisateur,
        email=commande.email,
        libelle=f"Commande {commande.numero}",
        montant_ttc=commande.total,
        taux_tva=Decimal(taux_tva),
    )
