"""
Ce qu'un paiement ouvre, et ce qu'un remboursement referme.

Un règlement encaissé ne vaut rien tant que la contrepartie n'est pas délivrée,
et une contrepartie délivrée deux fois vaut une réclamation. Tout passe donc
par ici, sous transaction et sous verrou : c'est le seul endroit qui décide
qu'un module s'ouvre, qu'une commande est réglée, qu'un dossier est à jour.

Le sens inverse compte autant. Rien, jusqu'ici, ne retirait un accès après un
remboursement ou une contestation bancaire — l'argent repartait, la formation
restait.
"""

from django.db import transaction
from django.utils import timezone

from apps.core.models import JournalAudit
from apps.core.services.audit import journaliser
from apps.paiements.models import Reglement


class ContrepartieImpossible(RuntimeError):
    """Le règlement est payé mais rien ne peut être délivré : cas à instruire."""


# ──────────────────────────────────────────────
# Délivrance
# ──────────────────────────────────────────────


@transaction.atomic
def delivrer(reglement: Reglement, *, acteur=None) -> Reglement:
    """Ouvre la contrepartie d'un règlement encaissé. Idempotent.

    Le verrou porte sur la ligne du règlement : deux notifications Stripe
    arrivant en parallèle — ce qui arrive — ne peuvent pas délivrer deux fois.
    """
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

    reglement.contrepartie_delivree = True
    reglement.save(update_fields=["contrepartie_delivree", "updated_at"])
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
    """L'achat d'un module ouvre un accès sans échéance.

    `duree_jours=None` est le choix commercial retenu : l'accès acheté est
    perpétuel. Le modèle sait poser une échéance, elle n'est simplement pas
    utilisée ici — la changer un jour se fera à cette ligne, pas ailleurs.
    """
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


def _delivrer_frais(reglement: Reglement, *, acteur=None) -> None:
    """Les frais d'inscription se consignent au dossier de l'étudiant."""
    from apps.academics.models import Paiement

    if reglement.etudiant is None:
        raise ContrepartieImpossible(f"Le règlement « {reglement.libelle} » n'est rattaché à aucun dossier étudiant.")
    Paiement.objects.update_or_create(
        reference=str(reglement.pk),
        defaults={
            "etudiant": reglement.etudiant,
            "montant": reglement.montant_ttc,
            "date_paiement": timezone.localdate(),
            "mode": Paiement.ModePaiement.CARTE,
            "statut": Paiement.StatutPaiement.CONFIRME,
        },
    )


def _delivrer_commande(reglement: Reglement, *, acteur=None) -> None:
    """Une commande réglée par carte est confirmée sans intervention humaine."""
    from apps.commerce.models import Commande
    from apps.commerce.services import confirmer_commande

    commande = reglement.commande
    if commande.statut != Commande.Statut.EN_ATTENTE:
        # Déjà confirmée à la main par le secrétariat : ne pas la bousculer.
        return
    confirmer_commande(commande, acteur=acteur)


# ──────────────────────────────────────────────
# Retrait
# ──────────────────────────────────────────────


@transaction.atomic
def retirer(reglement: Reglement, *, motif: str, acteur=None) -> Reglement:
    """Referme la contrepartie après remboursement ou contestation.

    Symétrique de `delivrer` : si rien n'avait été délivré, il n'y a rien à
    retirer, et l'appel reste sans effet.
    """
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

    inscription = InscriptionModule.objects.filter(etudiant=reglement.etudiant, module=reglement.module).first()
    if inscription is not None:
        octroi.revoquer(inscription, motif=motif, par=acteur)


def _retirer_frais(reglement: Reglement, *, motif: str, acteur=None) -> None:
    from apps.academics.models import Paiement

    Paiement.objects.filter(reference=str(reglement.pk)).update(statut=Paiement.StatutPaiement.REMBOURSE)


def _retirer_commande(reglement: Reglement, *, motif: str, acteur=None) -> None:
    from apps.commerce.models import Commande
    from apps.commerce.services import annuler_commande

    commande = reglement.commande
    if commande.statut in (Commande.Statut.EXPEDIEE, Commande.Statut.LIVREE):
        # Le colis est parti : l'annuler automatiquement remettrait en stock des
        # exemplaires qui n'y sont plus. Le secrétariat tranche.
        commande.statut_paiement = Commande.StatutPaiement.REMBOURSE
        commande.save(update_fields=["statut_paiement", "updated_at"])
        return
    annuler_commande(commande, acteur=acteur)
