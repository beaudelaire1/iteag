"""
Vues du paiement en ligne.

Une seule compte vraiment : le point d'entrée des notifications Stripe. Les
deux autres n'affichent qu'un état — elles ne décident de rien, et surtout pas
qu'un paiement a abouti.
"""

import logging

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from apps.paiements.models import Reglement
from apps.paiements.services import reglements, webhook
from apps.paiements.services.stripe_client import StripeIndisponible, creer_session, lire_evenement

logger = logging.getLogger(__name__)


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
    """Ouvre le paiement d'un module et envoie l'acheteur chez Stripe.

    En POST seulement : ouvrir une session de paiement est une action, pas une
    consultation, et un lien visité par erreur — ou préchargé par le navigateur
    — ne doit pas en créer une.
    """

    http_method_names = ["post"]

    def post(self, request, slug):
        from apps.elearning.models import ModuleFormation

        module = get_object_or_404(ModuleFormation, slug=slug)
        profil = getattr(request.user, "profil_etudiant", None)

        try:
            reglement = reglements.pour_module(module, profil, utilisateur=request.user)
            adresse = creer_session(reglement, request)
        except ValidationError as erreur:
            messages.error(request, erreur.messages[0])
        except StripeIndisponible:
            messages.error(
                request,
                "Le paiement par carte n'est pas disponible pour le moment. "
                "Contactez le secrétariat pour régler autrement.",
            )
        except Exception:
            logger.exception("Ouverture de session Stripe impossible pour le module %s", slug)
            messages.error(request, "Le service de paiement est momentanément injoignable. Réessayez.")
        else:
            return redirect(adresse)

        return redirect(module.get_absolute_url())
