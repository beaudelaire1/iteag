"""
Traitement des notifications Stripe — l'autorité sur l'état d'un règlement.

**La notification fait foi, jamais la redirection de retour.** L'étudiant ferme
son onglet, son réseau tombe, son téléphone se verrouille : la redirection
n'arrive pas, et il aurait payé sans rien recevoir. Stripe, lui, renotifie
jusqu'à obtenir un 2xx. C'est donc ici, et nulle part ailleurs, qu'un règlement
devient payé.

Trois propriétés sont exigées de ce module :

* **authenticité** — la signature est vérifiée en amont (`stripe_client`) ;
* **idempotence** — Stripe redélivre, et l'insertion en base de l'identifiant
  d'événement est ce qui départage deux livraisons concurrentes ; ce qui
  départage une redélivrance d'un rejeu, c'est le champ `traite` ;
* **acquittement honnête** — on ne répond 2xx que si l'on a réellement traité.
  Répondre 200 sur une erreur ferait taire Stripe et perdre l'encaissement.
"""

import logging

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.paiements.models import EvenementStripe, Reglement
from apps.paiements.services import attribution

logger = logging.getLogger(__name__)

# Les seuls événements qui nous concernent. Stripe en émet des dizaines : tout
# accepter reviendrait à écrire du bruit et à réagir à des transitions dont on
# ne maîtrise pas le sens.
EVENEMENTS_SUIVIS = frozenset(
    {
        "checkout.session.completed",
        "checkout.session.expired",
        "checkout.session.async_payment_failed",
        "charge.refunded",
        "charge.dispute.created",
    }
)


class EvenementDejaTraite(Exception):
    """Redélivrance d'un événement déjà pris en compte : rien à refaire."""


def traiter(evenement: dict) -> EvenementStripe | None:
    """Applique une notification Stripe déjà authentifiée.

    Retourne la trace enregistrée, ou `None` si l'événement ne nous concerne
    pas. Lève si le traitement échoue, afin que la vue réponde une erreur et
    que Stripe redélivre.
    """
    type_evenement = evenement.get("type", "")
    if type_evenement not in EVENEMENTS_SUIVIS:
        return None

    objet = evenement.get("data", {}).get("object", {})
    reglement = _retrouver_reglement(type_evenement, objet)

    # L'unicité en base est ce qui départage deux livraisons simultanées : on
    # ne consulte pas avant d'écrire, on écrit et on regarde qui a gagné. Un
    # test préalable laisserait passer les deux appels entre la lecture et
    # l'insertion.
    try:
        with transaction.atomic():
            trace = EvenementStripe.objects.create(
                identifiant=evenement["id"],
                type_evenement=type_evenement,
                reglement=reglement,
                charge_utile=evenement if isinstance(evenement, dict) else {},
            )
    except IntegrityError as erreur:
        # Une trace existe déjà — mais « déjà consignée » ne veut pas dire
        # « déjà traitée ». La trace est écrite avant l'action : si l'action a
        # échoué, la vue a répondu 500, Stripe a redélivré, et c'est ici que
        # l'on retombe. Lever sans regarder ferait répondre 200 à la seule
        # occasion de rattraper la livraison, et Stripe se tairait
        # définitivement sur un paiement encaissé sans contrepartie.
        #
        # On relit donc `traite`, qui n'avait jusqu'ici aucun lecteur. Rejouer
        # est sûr : `attribution.delivrer` est idempotent sous verrou.
        trace = EvenementStripe.objects.filter(identifiant=evenement["id"]).first()
        if trace is None or trace.traite:
            raise EvenementDejaTraite(evenement["id"]) from erreur
        logger.warning(
            "Notification Stripe %s consignée mais non traitée : rejeu de l'action.",
            evenement["id"],
        )
        if reglement is not None and trace.reglement_id is None:
            trace.reglement = reglement
            trace.save(update_fields=["reglement", "updated_at"])

    if reglement is None:
        trace.erreur = "Aucun règlement ne correspond à cette notification."
        trace.save(update_fields=["erreur", "updated_at"])
        logger.warning("Notification Stripe %s sans règlement associé.", evenement["id"])
        return trace

    actions = {
        "checkout.session.completed": _encaisser,
        "checkout.session.expired": _abandonner,
        "checkout.session.async_payment_failed": _echouer,
        "charge.refunded": _rembourser,
        "charge.dispute.created": _contester,
    }
    try:
        actions[type_evenement](reglement, objet)
    except Exception as erreur:
        trace.erreur = str(erreur)
        trace.save(update_fields=["erreur", "updated_at"])
        raise

    trace.traite = True
    trace.erreur = ""
    trace.save(update_fields=["traite", "erreur", "updated_at"])
    return trace


def _retrouver_reglement(type_evenement: str, objet: dict) -> Reglement | None:
    """Retrouve le règlement visé, quelle que soit la forme de l'événement.

    Une session Checkout porte notre propre identifiant dans
    `client_reference_id` — c'est la voie sûre. Un événement de charge, lui, ne
    connaît que le `payment_intent` : d'où la seconde piste.
    """
    reference = objet.get("client_reference_id")
    if reference:
        return Reglement.objects.filter(pk=reference).first()

    session = objet.get("id", "")
    if type_evenement.startswith("checkout.session") and session:
        return Reglement.objects.filter(session_stripe=session).first()

    intention = objet.get("payment_intent") or objet.get("id", "")
    if intention:
        return Reglement.objects.filter(intention_stripe=intention).first()
    return None


def _encaisser(reglement: Reglement, objet: dict) -> None:
    """Le paiement a abouti : on enregistre, puis on délivre.

    Le contrôle du montant n'est pas une précaution de style. La session est
    créée côté serveur, mais rien n'interdit qu'un règlement ait été modifié
    entre-temps : délivrer une formation à 300 € sur un encaissement de 3 €
    serait irrattrapable.
    """
    encaisse = objet.get("amount_total")
    if encaisse is not None and int(encaisse) != reglement.montant_en_centimes:
        raise ValueError(
            f"Montant encaissé ({encaisse}) différent du montant attendu "
            f"({reglement.montant_en_centimes}) pour le règlement {reglement.pk}."
        )
    if objet.get("payment_status") not in (None, "paid", "no_payment_required"):
        return

    reglement.statut = Reglement.Statut.PAYE
    reglement.intention_stripe = objet.get("payment_intent") or reglement.intention_stripe
    reglement.date_paiement = reglement.date_paiement or timezone.now()
    reglement.save(update_fields=["statut", "intention_stripe", "date_paiement", "updated_at"])
    attribution.delivrer(reglement)


def _abandonner(reglement: Reglement, objet: dict) -> None:
    if reglement.statut == Reglement.Statut.EN_ATTENTE:
        reglement.statut = Reglement.Statut.ABANDONNE
        reglement.save(update_fields=["statut", "updated_at"])


def _echouer(reglement: Reglement, objet: dict) -> None:
    reglement.statut = Reglement.Statut.ECHOUE
    reglement.motif_echec = "Le paiement différé a échoué."
    reglement.save(update_fields=["statut", "motif_echec", "updated_at"])


def _rembourser(reglement: Reglement, objet: dict) -> None:
    """Un remboursement partiel ne referme rien : l'accès reste dû."""
    if not objet.get("refunded", True):
        return
    reglement.statut = Reglement.Statut.REMBOURSE
    reglement.date_remboursement = timezone.now()
    reglement.save(update_fields=["statut", "date_remboursement", "updated_at"])
    attribution.retirer(reglement, motif="Remboursement du paiement en ligne.")


def _contester(reglement: Reglement, objet: dict) -> None:
    """Contestation bancaire : l'accès se referme sans attendre l'arbitrage.

    Rouvrir un accès coûte un clic ; laisser consommer une formation contestée
    coûte la formation.
    """
    reglement.statut = Reglement.Statut.LITIGE
    reglement.save(update_fields=["statut", "updated_at"])
    attribution.retirer(reglement, motif="Paiement contesté auprès de la banque.")
