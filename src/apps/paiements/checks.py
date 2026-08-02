"""Contrôles de configuration du paiement en ligne."""

from django.conf import settings
from django.core.checks import Error, Warning, register


@register()
def configuration_stripe(app_configs, **kwargs):
    """Une configuration Stripe à moitié faite encaisse sans délivrer.

    C'est le scénario à empêcher : la clé secrète suffit à ouvrir une session de
    paiement, mais sans secret de signature aucune notification n'est acceptée.
    L'étudiant paie, et rien ne s'ouvre. Mieux vaut refuser de démarrer.
    """
    secrete = getattr(settings, "STRIPE_CLE_SECRETE", "")
    webhook = getattr(settings, "STRIPE_SECRET_WEBHOOK", "")
    publiable = getattr(settings, "STRIPE_CLE_PUBLIABLE", "")

    if not any([secrete, webhook, publiable]):
        return [
            Warning(
                "Le paiement en ligne n'est pas configuré.",
                hint="Renseignez STRIPE_CLE_SECRETE, STRIPE_SECRET_WEBHOOK et STRIPE_CLE_PUBLIABLE "
                "pour encaisser par carte. Sans elles, seuls le virement et le paiement sur place "
                "restent proposés.",
                id="paiements.W001",
            )
        ]

    anomalies = []
    if secrete and not webhook:
        anomalies.append(
            Error(
                "STRIPE_SECRET_WEBHOOK est absent alors que Stripe est activé.",
                hint="Sans ce secret, aucune notification de paiement n'est acceptée : "
                "les règlements seraient encaissés sans jamais être délivrés.",
                id="paiements.E001",
            )
        )
    if webhook and not secrete:
        anomalies.append(
            Error(
                "STRIPE_CLE_SECRETE est absent alors qu'un secret de webhook est défini.",
                hint="La clé secrète est nécessaire pour ouvrir une session de paiement.",
                id="paiements.E002",
            )
        )
    if secrete and not settings.DEBUG and secrete.startswith("sk_test_"):
        # Une instance de recette doit pouvoir dérouler un paiement de bout en
        # bout avec les cartes de test ; l'erreur reste la règle par défaut pour
        # qu'une production ne puisse pas démarrer en mode test par oubli.
        if getattr(settings, "PAIEMENTS_AUTORISER_CLES_TEST", False):
            anomalies.append(
                Warning(
                    "Clés Stripe de test acceptées : instance de recette.",
                    hint="Aucun paiement n'est réellement encaissé. Retirez "
                    "PAIEMENTS_AUTORISER_CLES_TEST avant la mise en production.",
                    id="paiements.W002",
                )
            )
        else:
            anomalies.append(
                Error(
                    "Une clé Stripe de test est utilisée hors développement.",
                    hint="Les paiements ne seraient jamais réellement encaissés. "
                    "Utilisez la clé « sk_live_… » en production.",
                    id="paiements.E003",
                )
            )
    return anomalies
