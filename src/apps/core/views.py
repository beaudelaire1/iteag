"""Vues transverses : notifications, newsletter, sonde de santé."""

import secrets

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View
from django.views.generic import ListView

from apps.core.forms import NewsletterForm
from apps.core.models import AbonneNewsletter, Notification
from apps.core.services import notifications as service_notifications
from apps.core.services.audit import journaliser
from apps.core.services.emails import envoyer_email

# ──────────────────────────────────────────────
# Notifications — ETU-009
# ──────────────────────────────────────────────


class NotificationListView(LoginRequiredMixin, ListView):
    template_name = "core/notifications.html"
    context_object_name = "notifications"
    paginate_by = 25

    def get_queryset(self):
        return Notification.objects.filter(destinataire=self.request.user)

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        contexte["nb_non_lues"] = service_notifications.compter_non_lues(self.request.user)
        return contexte


class NotificationMarquerLueView(LoginRequiredMixin, View):
    http_method_names = ["post"]

    def post(self, request, pk):
        notification = get_object_or_404(Notification, pk=pk, destinataire=request.user)
        notification.marquer_lue()
        if notification.url_cible:
            return redirect(notification.url_cible)
        return redirect(reverse("core:notifications"))


class NotificationToutMarquerLuView(LoginRequiredMixin, View):
    http_method_names = ["post"]

    def post(self, request):
        nombre = service_notifications.marquer_tout_lu(request.user)
        messages.success(request, f"{nombre} notification(s) marquée(s) comme lue(s).")
        return redirect(reverse("core:notifications"))


class NotificationSupprimerView(LoginRequiredMixin, View):
    """Retire une notification de la liste de son destinataire.

    Marquer lu ne suffit pas : une notification traitée reste à l'écran et
    repousse les suivantes. La suppression ne porte que sur l'avis, jamais sur
    ce qu'il annonçait — le dossier, la copie ou la commande restent.

    Le filtre sur le destinataire est la garde : sans lui, un identifiant
    deviné suffirait à effacer l'avis d'un autre.
    """

    http_method_names = ["post"]

    def post(self, request, pk):
        notification = get_object_or_404(Notification, pk=pk, destinataire=request.user)
        notification.delete()
        if request.headers.get("HX-Request"):
            # La ligne disparaît sans recharger la page ; le gabarit remplace
            # l'élément par la réponse vide.
            return HttpResponse(status=200)
        messages.success(request, "Notification supprimée.")
        return redirect(reverse("core:notifications"))


class NotificationToutSupprimerView(LoginRequiredMixin, View):
    """Vide la liste des notifications déjà lues.

    Les non lues sont épargnées : les effacer en bloc ferait disparaître ce
    qu'on n'a pas encore vu.
    """

    http_method_names = ["post"]

    def post(self, request):
        nombre, _ = Notification.objects.filter(destinataire=request.user, lu=True).delete()
        messages.success(request, f"{nombre} notification(s) lue(s) supprimée(s).")
        return redirect(reverse("core:notifications"))


# ──────────────────────────────────────────────
# Newsletter — PUB-012
# ──────────────────────────────────────────────


def _retour_newsletter(request) -> str:
    """N'autorise le retour qu'à l'intérieur de l'origine courante."""

    propose = request.POST.get("suivant") or "/"
    if url_has_allowed_host_and_scheme(
        propose,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return propose
    return "/"


class NewsletterInscriptionView(View):
    """Inscription avec double consentement.

    La réponse est volontairement identique que l'adresse soit déjà inscrite ou
    non : la page ne doit pas permettre de tester l'appartenance à la liste.
    """

    def post(self, request):
        formulaire = NewsletterForm(request.POST)
        retour = _retour_newsletter(request)

        if not formulaire.is_valid():
            messages.error(request, "Merci de saisir une adresse email valide.")
            return redirect(retour)

        email = formulaire.cleaned_data["email"]
        abonne, cree = AbonneNewsletter.objects.get_or_create(email=email)

        if cree or not abonne.confirme:
            if not cree:
                # Nouveau jeton à chaque relance : un lien ancien cesse d'être valable.
                abonne.token_confirmation = ""
                abonne.save()
            lien = request.build_absolute_uri(
                reverse("core:newsletter_confirmation", kwargs={"token": abonne.token_confirmation})
            )
            envoyer_email(
                sujet="Confirmez votre inscription à la lettre d'information",
                gabarit="core/emails/newsletter_confirmation.html",
                contexte={"lien_confirmation": lien, "email": email},
                destinataires=[email],
            )
        elif not abonne.actif:
            abonne.actif = True
            abonne.date_desinscription = None
            abonne.save(update_fields=["actif", "date_desinscription", "updated_at"])

        messages.success(
            request,
            "Merci. Si cette adresse peut être inscrite, un email de confirmation vient de lui être envoyé.",
        )
        return redirect(retour)


class NewsletterConfirmationView(View):
    def get(self, request, token):
        abonne = get_object_or_404(AbonneNewsletter, token_confirmation=token)
        abonne.confirmer()
        journaliser(
            "creation",
            request=request,
            objet=abonne,
            objet_libelle=f"Newsletter : {abonne.email}",
        )
        return render(request, "core/newsletter_confirme.html", {"abonne": abonne})


class NewsletterDesinscriptionView(View):
    def get(self, request, token):
        abonne = get_object_or_404(AbonneNewsletter, token_desinscription=token)
        abonne.desinscrire()
        return render(request, "core/newsletter_desinscrit.html", {"abonne": abonne})


# ──────────────────────────────────────────────
# Sonde de santé
# ──────────────────────────────────────────────


class HealthzView(View):
    """État des dépendances, pour la supervision et le HEALTHCHECK du conteneur.

    **Arbitrage retenu le 9 août 2026** — la sonde reste publique, mais son
    détail ne l'est pas nécessairement.

    Fermer l'adresse elle-même a été écarté : le HEALTHCHECK du conteneur, le
    routage de Coolify et n'importe quelle supervision externe s'appuient sur
    son code de réponse. La restreindre par réseau obligerait à la rouvrir à
    chacun d'eux, et une sonde que la supervision ne peut pas joindre ne
    supervise rien.

    Ce qui méritait d'être protégé n'est pas l'existence de la panne — un 503
    la révèle de toute façon — mais **sa nature** : dire publiquement « la base
    répond, le cache non » renseigne un attaquant sur ce qu'il vient de faire
    tomber. Le code de réponse reste donc toujours lisible, et le détail par
    dépendance n'est servi qu'à qui présente `HEALTHZ_JETON` dans l'en-tête
    `X-Healthz-Token`.

    Sans jeton configuré — le défaut — le comportement est celui d'avant : tout
    est public. C'est une position tenable pour une sonde qui n'expose que deux
    booléens ; c'est à l'exploitant de la retenir ou de poser un jeton selon la
    supervision qu'il met en place. Le §3 du runbook porte la décision.
    """

    EN_TETE_JETON = "HTTP_X_HEALTHZ_TOKEN"

    def get(self, request):
        etats = {"base": self._base(), "cache": self._cache()}
        tout_va_bien = all(etats.values())
        corps = {"statut": "ok" if tout_va_bien else "degrade"}
        if self._detail_autorise(request):
            corps.update(etats)
        return JsonResponse(corps, status=200 if tout_va_bien else 503)

    @classmethod
    def _detail_autorise(cls, request) -> bool:
        jeton_attendu = str(getattr(settings, "HEALTHZ_JETON", "") or "")
        if not jeton_attendu:
            return True
        presente = request.META.get(cls.EN_TETE_JETON, "")
        # Comparaison à temps constant : la sonde est publique et répond vite,
        # ce qui en ferait un oracle commode pour deviner le jeton octet à octet.
        return secrets.compare_digest(str(presente), jeton_attendu)

    @staticmethod
    def _base() -> bool:
        from django.db import connection

        try:
            with connection.cursor() as curseur:
                curseur.execute("SELECT 1")
            return True
        except Exception:  # noqa: BLE001
            return False

    @staticmethod
    def _cache() -> bool:
        from django.core.cache import cache

        try:
            cache.set("healthz", "1", 5)
            return cache.get("healthz") == "1"
        except Exception:  # noqa: BLE001
            return False


# ──────────────────────────────────────────────
# Pages d'erreur
# ──────────────────────────────────────────────


def erreur_400(request, exception=None):
    return _rendre_erreur(request, 400, "Requête invalide", "La demande n'a pas pu être interprétée.")


def erreur_403(request, exception=None):
    return _rendre_erreur(
        request,
        403,
        "Accès refusé",
        "Vous n'avez pas les droits nécessaires pour consulter cette page.",
    )


def erreur_404(request, exception=None):
    return _rendre_erreur(
        request,
        404,
        "Page introuvable",
        "Cette page n'existe pas ou a été déplacée.",
    )


def erreur_500(request):
    return _rendre_erreur(
        request,
        500,
        "Une erreur est survenue",
        "Le service a rencontré un problème. L'équipe technique en a été informée.",
    )


def _rendre_erreur(request, code, titre, explication):
    return render(
        request,
        "core/erreur.html",
        {"code": code, "titre_erreur": titre, "explication": explication},
        status=code,
    )
