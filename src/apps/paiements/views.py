"""
Vues du paiement en ligne.

Le webhook reste la voie principale. La page de retour relit également la
session auprès de Stripe afin qu'un paiement déjà réussi ne reste pas bloqué si
la notification serveur est retardée.
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
from apps.paiements.services import reconciliation, reglements, webhook
from apps.paiements.services.reconciliation import SessionCheckoutIncoherente
from apps.paiements.services.stripe_client import (
    SessionPaiementTerminee,
    StripeIndisponible,
    creer_session_integree,
    est_configure,
    lire_evenement,
    recuperer_session_checkout,
)

logger = logging.getLogger(__name__)


def _reglement_visible(request, pk):
    """Retrouve un règlement sans exposer celui d'un autre compte."""
    filtres = Q(utilisateur__isnull=True)
    if request.user.is_authenticated:
        filtres |= Q(utilisateur=request.user)
    return get_object_or_404(
        Reglement.objects.select_related(
            "commande",
            "module",
            "inscription_associee__demande__cours_session__cours",
            "inscription_associee__demande__cours_session__session",
        ).prefetch_related("commande__lignes"),
        filtres,
        pk=pk,
    )


@method_decorator(csrf_exempt, name="dispatch")
class WebhookStripeView(View):
    """Réception authentifiée des notifications Stripe."""

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
            logger.warning("Signature Stripe refusée : %s", erreur)
            return HttpResponseBadRequest("Signature invalide.")

        try:
            trace = webhook.traiter(evenement)
        except webhook.EvenementDejaTraite:
            return HttpResponse(status=200)
        except Exception:
            logger.exception(
                "Échec du traitement de la notification Stripe %s",
                evenement.get("id"),
            )
            return HttpResponse("Traitement impossible.", status=500)

        if trace is None:
            return HttpResponse("Événement ignoré.", status=200)
        return HttpResponse(status=200)


class SuccesView(View):
    """Retour Stripe avec réconciliation serveur immédiate."""

    def get(self, request, pk):
        reglement = _reglement_visible(request, pk)
        session_id = request.GET.get("session_id", "").strip() or reglement.session_stripe

        if not reglement.est_paye and session_id:
            try:
                session_checkout = recuperer_session_checkout(session_id)
                reglement = reconciliation.synchroniser_depuis_checkout(
                    reglement,
                    session_checkout,
                )
            except (StripeIndisponible, SessionCheckoutIncoherente, ValueError) as erreur:
                logger.warning(
                    "Réconciliation Stripe refusée pour le règlement %s : %s",
                    reglement.pk,
                    erreur,
                )
            except Exception:
                logger.exception(
                    "Réconciliation Stripe impossible pour le règlement %s",
                    reglement.pk,
                )

        return render(
            request,
            "paiements/succes.html",
            {"reglement": reglement, "confirme": reglement.est_paye},
        )


class AnnulationView(View):
    def get(self, request, pk):
        reglement = _reglement_visible(request, pk)
        return render(request, "paiements/annulation.html", {"reglement": reglement})


class AchatModuleView(LoginRequiredMixin, View):
    """Prépare le paiement d'un module et ouvre la page sécurisée ITEAG.

    Un module est un contenu numérique dont l'accès s'ouvre dès l'encaissement.
    L'article L221-28 du code de la consommation ne fait tomber le droit de
    rétractation que si l'acheteur a **expressément** demandé cette exécution
    immédiate et reconnu y renoncer. Sans cette double déclaration, l'ITEAG
    devrait rembourser pendant quatorze jours un contenu déjà consultable.

    Le contrôle est refait ici et pas seulement dans le gabarit : une case à
    cocher retirée du DOM ne doit pas suffire à sauter la déclaration.
    """

    http_method_names = ["post"]
    CHAMP_RENONCIATION = "renonce_retractation"

    def post(self, request, slug):
        from apps.elearning.models import ModuleFormation

        module = get_object_or_404(ModuleFormation, slug=slug)
        profil = getattr(request.user, "profil_etudiant", None)

        if not request.POST.get(self.CHAMP_RENONCIATION):
            messages.error(
                request,
                "Pour acheter ce module, confirmez que vous demandez l'ouverture "
                "immédiate de l'accès et que vous renoncez de ce fait à votre "
                "droit de rétractation.",
            )
            return redirect(module.get_absolute_url())

        try:
            reglement = reglements.pour_module(
                module,
                profil,
                utilisateur=request.user,
            )
        except ValidationError as erreur:
            messages.error(request, erreur.messages[0])
        except Exception:
            logger.exception("Préparation du paiement impossible pour le module %s", slug)
            messages.error(
                request,
                "Le paiement ne peut pas être préparé pour le moment. Réessayez.",
            )
        else:
            return redirect("paiements:checkout", pk=reglement.pk)

        return redirect(module.get_absolute_url())


class PaiementInscriptionView(LoginRequiredMixin, View):
    """Ouvre le paiement de la demande appartenant à l'étudiant connecté."""

    http_method_names = ["post"]

    def post(self, request, pk):
        from apps.academics.models import DemandeInscriptionCours, Paiement

        demande = get_object_or_404(
            DemandeInscriptionCours.objects.select_related(
                "etudiant__utilisateur",
                "cours_session__cours",
                "cours_session__session",
                "paiement",
            ),
            pk=pk,
            etudiant__utilisateur=request.user,
        )

        if demande.paiement_id and demande.paiement.statut == Paiement.StatutPaiement.CONFIRME:
            messages.info(
                request,
                "Votre paiement a déjà été reçu. L'inscription attend la validation du secrétariat.",
            )
            return redirect("etudiant:enrollment_requests")

        try:
            reglement = reglements.pour_demande_inscription(
                demande,
                utilisateur=request.user,
            )
        except ValidationError as erreur:
            messages.error(request, erreur.messages[0])
            return redirect("etudiant:enrollment_requests")
        except Exception:
            logger.exception(
                "Préparation du paiement impossible pour la demande %s",
                demande.pk,
            )
            messages.error(
                request,
                "Le paiement ne peut pas être préparé pour le moment. Réessayez dans un instant.",
            )
            return redirect("etudiant:enrollment_requests")

        return redirect("paiements:checkout", pk=reglement.pk)


class PaiementCommandeView(View):
    """Prépare le paiement d'une commande, y compris pour un acheteur invité."""

    http_method_names = ["post"]

    def post(self, request, jeton):
        from apps.commerce.models import Commande

        commande = get_object_or_404(Commande, jeton_suivi=jeton)
        if commande.mode_paiement != Commande.ModePaiement.CARTE:
            messages.error(
                request,
                "Cette commande n'a pas été configurée pour un paiement par carte.",
            )
            return redirect(commande)
        if commande.statut_paiement == Commande.StatutPaiement.CONFIRME:
            messages.info(request, "Cette commande est déjà réglée.")
            return redirect(commande)

        try:
            reglement = reglements.pour_commande(commande)
        except ValidationError as erreur:
            messages.error(request, erreur.messages[0])
        except Exception:
            logger.exception(
                "Préparation du paiement impossible pour la commande %s",
                commande.numero,
            )
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

        association = getattr(reglement, "inscription_associee", None)
        demande_inscription = association.demande if association else None

        if reglement.nature == Reglement.Nature.COMMANDE:
            retour = reglement.commande.get_absolute_url()
        elif reglement.module_id:
            retour = reglement.module.get_absolute_url()
        elif demande_inscription is not None:
            retour = reverse("etudiant:enrollment_requests")
        else:
            retour = "/"

        return render(
            request,
            "paiements/checkout.html",
            {
                "reglement": reglement,
                "commande": reglement.commande,
                "demande_inscription": demande_inscription,
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
            logger.exception(
                "Ouverture de la session Stripe intégrée impossible pour %s",
                reglement.pk,
            )
            return JsonResponse(
                {"message": "Le paiement ne peut pas être chargé. Réessayez dans un instant."},
                status=502,
            )

        return JsonResponse({"client_secret": secret_client})
