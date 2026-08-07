"""Réconciliation serveur d'une session Checkout avec un règlement local."""

from django.db import transaction
from django.utils import timezone

from apps.paiements.models import Reglement
from apps.paiements.services import attribution


class SessionCheckoutIncoherente(ValueError):
    """La session Stripe reçue ne correspond pas au règlement demandé."""


def _valeur(objet, cle, defaut=None):
    if isinstance(objet, dict):
        return objet.get(cle, defaut)
    return getattr(objet, cle, defaut)


@transaction.atomic
def synchroniser_depuis_checkout(reglement: Reglement, session_checkout) -> Reglement:
    """Confirme un règlement depuis une session récupérée directement chez Stripe.

    Cette voie complète le webhook : elle est utilisée au retour du navigateur
    pour éviter qu'un paiement par carte déjà réussi reste indéfiniment en
    attente lorsque la notification Stripe est retardée ou mal routée.
    """
    reglement = Reglement.objects.select_for_update().get(pk=reglement.pk)

    identifiant_session = str(_valeur(session_checkout, "id", "") or "")
    reference = str(_valeur(session_checkout, "client_reference_id", "") or "")
    if not identifiant_session or identifiant_session != reglement.session_stripe:
        raise SessionCheckoutIncoherente("La session Stripe ne correspond pas à ce règlement.")
    if reference and reference != str(reglement.pk):
        raise SessionCheckoutIncoherente("La référence Stripe ne correspond pas à ce règlement.")

    montant = _valeur(session_checkout, "amount_total")
    if montant is not None and int(montant) != reglement.montant_en_centimes:
        raise SessionCheckoutIncoherente("Le montant Stripe ne correspond pas au montant attendu.")

    statut_paiement = _valeur(session_checkout, "payment_status", "")
    if statut_paiement not in {"paid", "no_payment_required"}:
        return reglement

    if reglement.statut != Reglement.Statut.PAYE:
        reglement.statut = Reglement.Statut.PAYE
        reglement.intention_stripe = _valeur(session_checkout, "payment_intent", "") or reglement.intention_stripe
        reglement.date_paiement = reglement.date_paiement or timezone.now()
        reglement.save(
            update_fields=[
                "statut",
                "intention_stripe",
                "date_paiement",
                "updated_at",
            ]
        )

    attribution.delivrer(reglement)
    return Reglement.objects.get(pk=reglement.pk)
