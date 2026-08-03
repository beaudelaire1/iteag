"""
Frontière avec Stripe — le seul endroit qui connaisse leur bibliothèque.

Tout le reste de l'application manipule des `Reglement`. Ce module traduit dans
les deux sens, et rien d'autre : aucune règle métier ici, aucune écriture en
base. C'est ce qui rend le reste testable sans appeler le réseau.
"""

from django.conf import settings
from django.urls import reverse

# Le paiement en ligne est facultatif : un déploiement peut n'encaisser que par
# virement. L'import ne doit donc pas casser une installation sans Stripe.
try:
    import stripe
except ImportError:  # pragma: no cover — dépendance déclarée dans base.txt
    stripe = None


class StripeIndisponible(RuntimeError):
    """Stripe n'est pas configuré : mieux vaut le dire que d'échouer plus loin."""


class SessionPaiementTerminee(RuntimeError):
    """La session Stripe a déjà abouti et ne doit pas être remplacée."""


def est_configure() -> bool:
    """Stripe peut-il encaisser ?

    Le secret de signature en fait partie. Sans lui, on saurait créer une
    session de paiement mais pas vérifier qu'elle a abouti : on encaisserait
    sans jamais délivrer. Une configuration à moitié faite est pire qu'absente.
    """
    return bool(
        stripe is not None
        and getattr(settings, "STRIPE_CLE_SECRETE", "")
        and getattr(settings, "STRIPE_SECRET_WEBHOOK", "")
    )


def _client():
    if not est_configure():
        raise StripeIndisponible("Stripe n'est pas configuré. Renseignez STRIPE_CLE_SECRETE et STRIPE_SECRET_WEBHOOK.")
    stripe.api_key = settings.STRIPE_CLE_SECRETE
    return stripe


def _adresse_absolue(request, nom_url: str, **kwargs) -> str:
    chemin = reverse(nom_url, kwargs=kwargs)
    if request is not None:
        return request.build_absolute_uri(chemin)
    return f"{getattr(settings, 'SITE_URL', '').rstrip('/')}{chemin}"


def creer_session_integree(reglement, request=None) -> str:
    """Ouvre ou reprend une session Checkout intégrée et renvoie son secret client.

    Une session encore ouverte est réutilisée après un rechargement de page.
    Une ancienne session hébergée ou expirée est remplacée, mais sa clé sert à
    rendre cette opération idempotente : deux appels simultanés ne peuvent pas
    produire deux possibilités d'encaissement distinctes.
    """
    client = _client()
    session_precedente = None

    if reglement.session_stripe:
        session_precedente = client.checkout.Session.retrieve(reglement.session_stripe)
        statut = getattr(session_precedente, "status", "")
        paiement = getattr(session_precedente, "payment_status", "")
        secret_client = getattr(session_precedente, "client_secret", "")
        mode_interface = getattr(session_precedente, "ui_mode", "")

        if paiement == "paid" or statut == "complete":
            raise SessionPaiementTerminee("Ce paiement a déjà été traité.")
        if statut == "open" and mode_interface == "embedded" and secret_client:
            return secret_client
        if statut == "open":
            client.checkout.Session.expire(reglement.session_stripe)

    retour = f"{_adresse_absolue(request, 'paiements:succes', pk=reglement.pk)}?session_id={{CHECKOUT_SESSION_ID}}"
    identifiant_precedent = getattr(session_precedente, "id", "") or "initiale"
    session = client.checkout.Session.create(
        ui_mode="embedded",
        mode="payment",
        locale="fr",
        payment_method_types=["card"],
        client_reference_id=str(reglement.pk),
        customer_email=reglement.email or None,
        line_items=[
            {
                "quantity": 1,
                "price_data": {
                    "currency": reglement.devise.lower(),
                    "unit_amount": reglement.montant_en_centimes,
                    "product_data": {"name": reglement.libelle},
                },
            }
        ],
        metadata={
            "reglement": str(reglement.pk),
            "nature": reglement.nature,
            "taux_tva": str(reglement.taux_tva),
        },
        return_url=retour,
        idempotency_key=f"reglement-{reglement.pk}-integre-apres-{identifiant_precedent}",
    )
    reglement.session_stripe = session.id
    reglement.save(update_fields=["session_stripe", "updated_at"])
    return session.client_secret


def lire_evenement(charge_utile: bytes, signature: str):
    """Authentifie une notification Stripe et la renvoie décodée.

    C'est le contrôle qui empêche un tiers de déclarer un paiement abouti en
    postant du JSON à notre adresse publique. Une signature invalide lève, et
    l'appelant répond 400 sans rien écrire.
    """
    client = _client()
    return client.Webhook.construct_event(
        payload=charge_utile,
        sig_header=signature,
        secret=settings.STRIPE_SECRET_WEBHOOK,
    )
