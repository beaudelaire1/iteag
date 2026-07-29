"""
Vues du paiement en ligne.

Une seule compte vraiment : le point d'entrée des notifications Stripe. Les
deux autres n'affichent qu'un état — elles ne décident de rien, et surtout pas
qu'un paiement a abouti.
"""

import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from apps.paiements.models import Reglement
from apps.paiements.services import reglements, webhook
from apps.paiements.services.stripe_client import (
    SessionPaiementTerminee,
    StripeIndisponible,
    creer_session_integree,
    est_configure,
    lire_evenement,
)

logger = logging.getLogger(__name__)


def _reglement_visible(request, pk):
    """Retrouve un règlement sans exposer celui d'un autre compte."""
    filtres = Q(utilisateur__isnull=True)
    if request.user.is_authenticated:
        filtres |= Q(utilisateur=request.user)
    return get_object_or_404(
        Reglement.objects.select_related("commande", "module").prefetch_related("commande__lignes"),
        filtres,
        pk=pk,
    )


@method_decorator(csrf_exempt, name="dispatch")
class WebhookStripeView(View):
    """
    Réception des notifications Stripe.

    `csrf_exempt` est requis — Stripe n'a pas nos jetons — et sans danger : la
    protection ne vient pas du CSRF mais de la signature cryptographique, qui
    est vérifiée avant toute lecture du contenu. Un appel non signé ne franchit
    pas la première ligne utile.

    Le code de réponse est un engagement : 2xx signifie « pris en compte, ne
    renvoyez plus ». On ne le renvoie donc jamais par confort.
    """

    http_method_names = ["post"]

    def post(self, request):
        signature = request.META.get("HTTP_STRIPE_SIGNATURE", "")
        if not signature:
            return HttpResponseBadRequest("Signature absente.")

        try:
            evenement = lire_evenement(request.body, signature)
        except StripeIndisponible:
            logger.error("Notification Stripe reçue alors que Stripe n'est pas configuré.")
            return HttpResponse("Paiement en ligne non configuré.", status=503)
        except ValueError:
            return HttpResponseBadRequest("Contenu illisible.")
        except Exception as erreur:
            # `SignatureVerificationError` hérite de la hiérarchie Stripe ; on
            # ne l'importe pas pour garder ce module indépendant de leur API.
            logger.warning("Signature Stripe refusée : %s", erreur)
            return HttpResponseBadRequest("Signature invalide.")

        try:
            trace = webhook.traiter(evenement)
        except webhook.EvenementDejaTraite:
            # Redélivrance : déjà appliqué, donc acquitté sans rien refaire.
            return HttpResponse(status=200)
        except Exception:
            logger.exception("Échec du traitement de la notification Stripe %s", evenement.get("id"))
            # 500 volontaire : Stripe redélivrera, et l'encaissement ne sera pas
            # perdu. Un 200 complaisant le perdrait définitivement.
            return HttpResponse("Traitement impossible.", status=500)

        if trace is None:
            return HttpResponse("Événement ignoré.", status=200)
        return HttpResponse(status=200)


class SuccesView(View):
    """Page de retour après paiement — informative, jamais décisionnaire.

    Le règlement peut y apparaître « en attente » : la notification Stripe
    arrive parfois après la redirection du navigateur. C'est normal, et c'est
    dit à l'écran plutôt que masqué par un message de succès mensonger.
    """

    def get(self, request, pk):
        reglement = get_object_or_404(Reglement, pk=pk)
        return render(
            request,
            "paiements/succes.html",
            {"reglement": reglement, "confirme": reglement.est_paye},
        )


class AnnulationView(View):
    def get(self, request, pk):
        reglement = get_object_or_404(Reglement, pk=pk)
        return render(request, "paiements/annulation.html", {"reglement": reglement})


class AchatModuleView(LoginRequiredMixin, View):
    """Prépare le paiement d'un module et ouvre la page sécurisée ITEAG.

    En POST seulement : créer un règlement est une action, pas une consultation,
    et un lien préchargé par le navigateur ne doit pas en créer un.
    """

    http_method_names = ["post"]

    def post(self, request, slug):
        from apps.elearning.models import ModuleFormation

        module = get_object_or_404(ModuleFormation, slug=slug)
        profil = getattr(request.user, "profil_etudiant", None)

        try:
            reglement = reglements.pour_module(module, profil, utilisateur=request.user)
        except ValidationError as erreur:
            messages.error(request, erreur.messages[0])
        except Exception:
            logger.exception("Préparation du paiement impossible pour le module %s", slug)
            messages.error(request, "Le paiement ne peut pas être préparé pour le moment. Réessayez.")
        else:
            return redirect("paiements:checkout", pk=reglement.pk)

        return redirect(module.get_absolute_url())


class PaiementCommandeView(View):
    """Prépare le paiement d'une commande, y compris pour un acheteur invité."""

    http_method_names = ["post"]

    def post(self, request, jeton):
        from apps.commerce.models import Commande

        commande = get_object_or_404(Commande, jeton_suivi=jeton)
        if commande.mode_paiement != Commande.ModePaiement.CARTE:
            messages.error(request, "Cette commande n'a pas été configurée pour un paiement par carte.")
            return redirect(commande)
        if commande.statut_paiement == Commande.StatutPaiement.CONFIRME:
            messages.info(request, "Cette commande est déjà réglée.")
            return redirect(commande)

        try:
            reglement = reglements.pour_commande(commande)
        except ValidationError as erreur:
            messages.error(request, erreur.messages[0])
        except Exception:
            logger.exception("Préparation du paiement impossible pour la commande %s", commande.numero)
            messages.error(
                request,
                "Le paiement ne peut pas être préparé pour le moment. "
                "Votre commande reste enregistrée : réessayez dans un instant.",
            )
        else:
            return redirect("paiements:checkout", pk=reglement.pk)

        return redirect(commande)


class CheckoutView(View):
    """Page ITEAG qui accueille le formulaire bancaire sécurisé de Stripe."""

    http_method_names = ["get"]

    def get(self, request, pk):
        reglement = _reglement_visible(request, pk)
        if reglement.est_paye:
            return redirect("paiements:succes", pk=reglement.pk)

        if reglement.nature == Reglement.Nature.COMMANDE:
            retour = reglement.commande.get_absolute_url()
        elif reglement.module_id:
            retour = reglement.module.get_absolute_url()
        else:
            retour = "/"

        return render(
            request,
            "paiements/checkout.html",
            {
                "reglement": reglement,
                "commande": reglement.commande,
                "retour": retour,
                "stripe_configure": est_configure(),
                "stripe_cle_publiable": settings.STRIPE_CLE_PUBLIABLE,
            },
        )


class SessionCheckoutView(View):
    """Crée la session Stripe intégrée depuis la page, avec protection CSRF."""

    http_method_names = ["post"]

    def post(self, request, pk):
        reglement = _reglement_visible(request, pk)
        if reglement.est_paye:
            return JsonResponse(
                {"redirect_url": reverse("paiements:succes", kwargs={"pk": reglement.pk})},
                status=409,
            )

        try:
            secret_client = creer_session_integree(reglement, request)
        except SessionPaiementTerminee:
            return JsonResponse(
                {"redirect_url": reverse("paiements:succes", kwargs={"pk": reglement.pk})},
                status=409,
            )
        except StripeIndisponible:
            return JsonResponse(
                {"message": "Le paiement par carte est temporairement indisponible."},
                status=503,
            )
        except Exception:
            logger.exception("Ouverture de la session Stripe intégrée impossible pour %s", reglement.pk)
            return JsonResponse(
                {"message": "Le paiement ne peut pas être chargé. Réessayez dans un instant."},
                status=502,
            )

        return JsonResponse({"client_secret": secret_client})
