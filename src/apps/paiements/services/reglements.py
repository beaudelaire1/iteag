"""
Ouverture d'un règlement — un point d'entrée par nature.

Le prix n'est jamais lu depuis la requête. Il est relu en base au moment de
créer le règlement, et c'est lui que Stripe encaissera : un montant qui
transiterait par le navigateur serait un montant négociable par l'acheteur.
"""

from decimal import Decimal

from django.conf import settings
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
    """Règlement de frais administratifs fixé hors d'une demande de cours."""
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
def pour_demande_inscription(demande, *, utilisateur=None) -> Reglement:
    """Ouvre ou reprend le règlement de la demande d'inscription donnée.

    Une demande ne possède qu'un règlement durable. En cas d'échec ou de
    remboursement, une nouvelle session Stripe est ouverte sur ce même
    règlement afin de garder une référence financière unique.
    """
    from apps.academics.models import DemandeInscriptionCours, Paiement
    from apps.paiements.models_inscriptions import ReglementInscription

    # « paiement » est nullable : PostgreSQL refuse un FOR UPDATE appliqué au
    # côté nullable de la jointure externe produite par select_related(). Seule
    # la demande doit être verrouillée pour sérialiser la création du règlement.
    demande = (
        DemandeInscriptionCours.objects.select_for_update(of=("self",))
        .select_related(
            "etudiant__utilisateur",
            "cours_session__cours",
            "cours_session__session",
            "paiement",
        )
        .get(pk=demande.pk)
    )

    if demande.statut != DemandeInscriptionCours.Statut.PAIEMENT_ATTENTE:
        raise ValidationError("Cette demande n'est pas en attente de paiement.")
    if demande.montant_du <= 0:
        raise ValidationError("Aucun paiement n'est requis pour cette demande.")
    if demande.paiement_id and demande.paiement.statut == Paiement.StatutPaiement.CONFIRME:
        raise ValidationError("Le paiement de cette demande a déjà été reçu.")

    association = ReglementInscription.objects.select_related("reglement").filter(demande=demande).first()
    if association is not None:
        reglement = association.reglement
        if reglement.est_paye or reglement.statut == Reglement.Statut.EN_ATTENTE:
            return reglement

        reglement.statut = Reglement.Statut.EN_ATTENTE
        reglement.session_stripe = ""
        reglement.intention_stripe = ""
        reglement.date_paiement = None
        reglement.date_remboursement = None
        reglement.motif_echec = ""
        reglement.contrepartie_delivree = False
        reglement.save(
            update_fields=[
                "statut",
                "session_stripe",
                "intention_stripe",
                "date_paiement",
                "date_remboursement",
                "motif_echec",
                "contrepartie_delivree",
                "updated_at",
            ]
        )
        return reglement

    porteur, adresse = _payeur(
        utilisateur or demande.etudiant.utilisateur,
        demande.etudiant.utilisateur.email,
    )
    taux_tva = Decimal(str(getattr(settings, "PAIEMENTS_TAUX_TVA_DEFAUT", "0.00")))
    reglement = Reglement.objects.create(
        nature=Reglement.Nature.FRAIS_INSCRIPTION,
        etudiant=demande.etudiant,
        utilisateur=porteur,
        email=adresse,
        libelle=(
            f"Inscription — {demande.cours_session.cours.titre} "
            f"({demande.cours_session.session.nom})"
        ),
        montant_ttc=demande.montant_du,
        taux_tva=taux_tva,
    )
    ReglementInscription.objects.create(reglement=reglement, demande=demande)
    return reglement


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
