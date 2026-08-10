"""
Tâches planifiées du paiement — le filet sous le webhook.

Le webhook fait foi, mais il peut tomber : une base indisponible le temps d'une
requête, un module supprimé entre la création du règlement et son encaissement,
un dossier étudiant détaché. Dans ces cas-là, l'argent est encaissé et la
contrepartie ne part pas. Stripe redélivre, le rejeu du webhook rattrape la
plupart des cas — mais pas celui où l'erreur survit à la fenêtre de
redélivrance de Stripe.

`reparer_livraisons` est ce qui reste après Stripe. Elle ne remplace pas le
webhook : elle refuse de laisser un encaissement sans contrepartie passer
inaperçu, et prévient une personne quand elle n'y arrive pas elle-même.
"""

import logging
from datetime import timedelta

from django.conf import settings
from django.urls import reverse
from django.utils import timezone

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name="paiements.reparer_livraisons")
def reparer_livraisons() -> int:
    """Rejoue les livraisons manquées et signale celles qui résistent.

    Retourne le nombre de contreparties effectivement délivrées.
    """
    from apps.paiements.models import Reglement
    from apps.paiements.services import attribution

    delai = int(getattr(settings, "PAIEMENTS_DELAI_REPARATION_MINUTES", 15))
    seuil = int(getattr(settings, "PAIEMENTS_SEUIL_ALERTE_LIVRAISON", 2))
    limite = timezone.now() - timedelta(minutes=delai)

    # `date_paiement` plutôt que `created_at` : c'est l'encaissement qui ouvre
    # la dette de livraison, pas la création du règlement, qui peut précéder le
    # paiement de plusieurs jours.
    en_souffrance = Reglement.objects.filter(
        statut=Reglement.Statut.PAYE,
        contrepartie_delivree=False,
        date_paiement__lt=limite,
    ).order_by("date_paiement")

    reparees = 0
    for reglement in en_souffrance:
        try:
            attribution.delivrer(reglement)
        except Exception as erreur:  # noqa: BLE001 — un échec ne doit pas arrêter la tournée
            logger.exception("Rattrapage de livraison en échec pour le règlement %s", reglement.pk)
            _consigner_echec(reglement, erreur, seuil=seuil)
            continue
        reparees += 1
        logger.info("Livraison rattrapée pour le règlement %s", reglement.pk)

    if reparees:
        logger.info("Réparation des livraisons : %s contrepartie(s) délivrée(s)", reparees)
    return reparees


def _consigner_echec(reglement, erreur: Exception, *, seuil: int) -> None:
    """Incrémente le compteur d'échecs et alerte le secrétariat au seuil."""
    from apps.paiements.models import Reglement

    # Requête ciblée : `delivrer` a pu modifier l'objet en mémoire avant de
    # lever, et on ne veut réécrire que le compteur.
    reglement.tentatives_livraison = (reglement.tentatives_livraison or 0) + 1
    reglement.derniere_erreur_livraison = str(erreur)[:2000]
    Reglement.objects.filter(pk=reglement.pk).update(
        tentatives_livraison=reglement.tentatives_livraison,
        derniere_erreur_livraison=reglement.derniere_erreur_livraison,
        updated_at=timezone.now(),
    )

    if reglement.tentatives_livraison < seuil or reglement.livraison_signalee:
        return

    if _alerter_secretariat(reglement):
        Reglement.objects.filter(pk=reglement.pk).update(
            livraison_signalee=True,
            updated_at=timezone.now(),
        )


def _alerter_secretariat(reglement) -> bool:
    """Prévient le personnel qu'un encaissement n'a rien ouvert. Vrai si envoyé."""
    from django.contrib.auth import get_user_model

    from apps.core.models import Notification
    from apps.core.services.notifications import notifier_plusieurs

    # `get_user_model()` et non `apps.accounts.models` : l'architecture du
    # projet interdit à « paiements » de dépendre de « accounts », et cette
    # règle est tenue par un test. L'indirection de Django dit exactement ce
    # qu'on veut — le modèle utilisateur du projet — sans créer l'arête.
    User = get_user_model()
    personnel = User.objects.filter(
        is_active=True,
        role__in=[User.Role.ADMIN, User.Role.SECRETARIAT],
    )
    envois = notifier_plusieurs(
        personnel,
        f"Paiement encaissé sans contrepartie — {reglement.libelle}",
        type_notification=Notification.Type.SYSTEME,
        message=(
            f"Le règlement de {reglement.montant_ttc} {reglement.devise} pour "
            f"« {reglement.libelle} » est encaissé, mais la contrepartie n'a pas pu être "
            f"délivrée après {reglement.tentatives_livraison} tentatives automatiques. "
            "Le payeur a réglé et n'a rien reçu : ce cas demande une intervention manuelle. "
            "La procédure figure au §5 du runbook, « Un paiement est encaissé mais rien "
            "n'est délivré »."
        ),
        details=[
            {"libelle": "Référence du règlement", "valeur": str(reglement.pk)},
            {"libelle": "Payeur", "valeur": reglement.email},
            {"libelle": "Nature", "valeur": reglement.get_nature_display()},
            {"libelle": "Dernier échec", "valeur": reglement.derniere_erreur_livraison[:300] or "—"},
        ],
        url_cible=reverse("admin:paiements_reglement_change", args=[reglement.pk]),
    )
    if not envois:
        # Aucun destinataire actif : l'alerte n'a atteint personne. Le dire, et
        # ne pas marquer le règlement comme signalé — la prochaine tournée
        # réessaiera, ce qui vaut mieux qu'un incident classé sans lecteur.
        logger.error(
            "Aucun destinataire pour l'alerte de livraison du règlement %s : aucun compte admin ou secrétariat actif.",
            reglement.pk,
        )
        return False
    return True


@shared_task(name="paiements.minimiser_charges_utiles")
def minimiser_charges_utiles(jours: int | None = None) -> int:
    """Efface le corps des notifications Stripe devenues inutiles.

    Une session Checkout transporte `customer_details` : nom, adresse
    électronique, adresse postale, pays. Rien de tout cela n'est nécessaire
    passé le rapprochement comptable — alors que l'identifiant, le type, le
    règlement et l'indicateur de traitement le restent, pour l'idempotence
    comme pour la piste d'audit. On vide donc le corps, et lui seul.

    Un événement non traité n'est jamais vidé : sa charge utile est encore ce
    qui permettrait de le rejouer.
    """
    from apps.paiements.models import EvenementStripe

    if jours is None:
        jours = int(getattr(settings, "RETENTION_CHARGE_UTILE_STRIPE_JOURS", 90))
    limite = timezone.now() - timedelta(days=jours)

    nombre = (
        EvenementStripe.objects.filter(traite=True, created_at__lt=limite)
        .exclude(charge_utile={})
        .update(charge_utile={}, updated_at=timezone.now())
    )
    logger.info("Minimisation des charges utiles Stripe : %s événement(s) vidé(s)", nombre)
    return nombre
