"""
Ce qu'un paiement ouvre, et ce qu'un remboursement referme.

Un règlement encaissé ne vaut rien tant que la contrepartie n'est pas délivrée,
et une contrepartie délivrée deux fois vaut une réclamation. Tout passe donc
par ici, sous transaction et sous verrou : c'est le seul endroit qui décide
qu'un module s'ouvre, qu'une commande est réglée, qu'un dossier est à jour.
"""

from django.db import transaction
from django.utils import timezone

from apps.core.models import JournalAudit
from apps.core.services.audit import journaliser
from apps.paiements.models import Reglement


class ContrepartieImpossible(RuntimeError):
    """Le règlement est payé mais rien ne peut être délivré : cas à instruire."""


@transaction.atomic
def delivrer(reglement: Reglement, *, acteur=None) -> Reglement:
    """Ouvre la contrepartie d'un règlement encaissé. Idempotent."""
    reglement = Reglement.objects.select_for_update().get(pk=reglement.pk)
    if reglement.contrepartie_delivree:
        return reglement
    if reglement.statut != Reglement.Statut.PAYE:
        raise ContrepartieImpossible("Un règlement non payé n'ouvre aucune contrepartie.")

    livreurs = {
        Reglement.Nature.MODULE: _delivrer_module,
        Reglement.Nature.FRAIS_INSCRIPTION: _delivrer_frais,
        Reglement.Nature.COMMANDE: _delivrer_commande,
    }
    livreurs[reglement.nature](reglement, acteur=acteur)

    # La livraison a abouti : le compteur de rattrapage repart à zéro, faute de
    # quoi un règlement rattrapé au troisième essai resterait marqué comme un
    # incident ouvert.
    reglement.contrepartie_delivree = True
    reglement.tentatives_livraison = 0
    reglement.derniere_erreur_livraison = ""
    reglement.save(
        update_fields=[
            "contrepartie_delivree",
            "tentatives_livraison",
            "derniere_erreur_livraison",
            "updated_at",
        ]
    )
    journaliser(
        JournalAudit.Action.PAIEMENT_RECU,
        utilisateur=acteur or reglement.utilisateur,
        objet=reglement,
        objet_libelle=reglement.libelle,
        nature=reglement.nature,
        montant=str(reglement.montant_ttc),
    )
    return reglement


def _delivrer_module(reglement: Reglement, *, acteur=None) -> None:
    from apps.elearning.models import InscriptionModule
    from apps.elearning.services import octroi

    if reglement.etudiant is None:
        raise ContrepartieImpossible(f"Le règlement « {reglement.libelle} » n'est rattaché à aucun dossier étudiant.")
    octroi.octroyer(
        reglement.etudiant,
        reglement.module,
        source=InscriptionModule.SourceAcces.ACHAT,
        duree_jours=None,
        octroye_par=acteur,
    )


def _association_inscription(reglement):
    from apps.paiements.models_inscriptions import ReglementInscription

    return (
        ReglementInscription.objects.select_related(
            "demande__cours_session__session",
            "demande__paiement",
        )
        .filter(reglement=reglement)
        .first()
    )


def _delivrer_frais(reglement: Reglement, *, acteur=None) -> None:
    """Consigne les frais au dossier et les rattache à la bonne demande."""
    from apps.academics.models import Paiement

    if reglement.etudiant is None:
        raise ContrepartieImpossible(f"Le règlement « {reglement.libelle} » n'est rattaché à aucun dossier étudiant.")

    association = _association_inscription(reglement)
    session = association.demande.cours_session.session if association else None
    paiement, _ = Paiement.objects.update_or_create(
        reference=str(reglement.pk),
        defaults={
            "etudiant": reglement.etudiant,
            "session": session,
            "montant": reglement.montant_ttc,
            "date_paiement": timezone.localdate(),
            "mode": Paiement.ModePaiement.CARTE,
            "statut": Paiement.StatutPaiement.CONFIRME,
        },
    )

    if association is not None:
        demande = association.demande
        demande.paiement = paiement
        demande.reference_paiement = str(reglement.pk)
        demande.save(
            update_fields=[
                "paiement",
                "reference_paiement",
                "updated_at",
            ]
        )


def _delivrer_commande(reglement: Reglement, *, acteur=None) -> None:
    from apps.commerce.models import Commande
    from apps.commerce.services import confirmer_commande

    commande = reglement.commande
    if commande.statut != Commande.Statut.EN_ATTENTE:
        return
    confirmer_commande(commande, acteur=acteur)


@transaction.atomic
def retirer(reglement: Reglement, *, motif: str, acteur=None) -> Reglement:
    """Referme la contrepartie après remboursement ou contestation."""
    reglement = Reglement.objects.select_for_update().get(pk=reglement.pk)
    if not reglement.contrepartie_delivree:
        return reglement

    retireurs = {
        Reglement.Nature.MODULE: _retirer_module,
        Reglement.Nature.FRAIS_INSCRIPTION: _retirer_frais,
        Reglement.Nature.COMMANDE: _retirer_commande,
    }
    retireurs[reglement.nature](reglement, motif=motif, acteur=acteur)

    reglement.contrepartie_delivree = False
    reglement.save(update_fields=["contrepartie_delivree", "updated_at"])
    journaliser(
        JournalAudit.Action.PAIEMENT_REMBOURSE,
        utilisateur=acteur,
        objet=reglement,
        objet_libelle=reglement.libelle,
        nature=reglement.nature,
        motif=motif,
    )
    return reglement


def _retirer_module(reglement: Reglement, *, motif: str, acteur=None) -> None:
    from apps.elearning.models import InscriptionModule
    from apps.elearning.services import octroi

    inscription = InscriptionModule.objects.filter(
        etudiant=reglement.etudiant,
        module=reglement.module,
    ).first()
    if inscription is not None:
        octroi.revoquer(inscription, motif=motif, par=acteur)


def _retirer_frais(reglement: Reglement, *, motif: str, acteur=None) -> None:
    from apps.academics.models import DemandeInscriptionCours, Paiement

    paiement = Paiement.objects.filter(reference=str(reglement.pk)).first()
    if paiement is None:
        return

    paiement.statut = Paiement.StatutPaiement.REMBOURSE
    paiement.save(update_fields=["statut", "updated_at"])

    association = _association_inscription(reglement)
    if association is None:
        return

    demande = association.demande
    if demande.statut == DemandeInscriptionCours.Statut.PAIEMENT_ATTENTE and demande.paiement_id == paiement.pk:
        demande.paiement = None
        demande.reference_paiement = ""
        demande.save(
            update_fields=[
                "paiement",
                "reference_paiement",
                "updated_at",
            ]
        )


def _retirer_commande(reglement: Reglement, *, motif: str, acteur=None) -> None:
    from apps.commerce.models import Commande
    from apps.commerce.services import annuler_commande

    commande = reglement.commande
    if commande.statut in (Commande.Statut.EXPEDIEE, Commande.Statut.LIVREE):
        commande.statut_paiement = Commande.StatutPaiement.REMBOURSE
        commande.save(update_fields=["statut_paiement", "updated_at"])
        return
    annuler_commande(
        commande,
        acteur=acteur,
        motif=Commande.MotifAnnulation.PAIEMENT_NON_RECU,
        precision=motif,
    )
