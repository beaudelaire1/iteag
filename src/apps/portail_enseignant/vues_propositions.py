"""Les cours qu'on propose à l'enseignant, et sa réponse.

L'administration désignait jusqu'ici l'enseignant d'un cours sans le lui
demander : il le découvrait sur son tableau de bord, et un refus se réglait
hors de la plateforme. Il dispose ici de sa file de propositions, qu'il accepte
ou décline en disant pourquoi.
"""

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views import View
from django.views.generic import TemplateView

from apps.academics.models import PropositionEnseignement
from apps.core.mixins import TeacherRoleRequiredMixin
from apps.core.models import Notification
from apps.core.services.notifications import notifier


def _fiche_du_compte(utilisateur):
    """La fiche professeur rattachée au compte, sans laquelle rien n'est à lui."""
    professeur = getattr(utilisateur, "profil_professeur", None)
    if professeur is None:
        raise Http404("Aucune fiche enseignant n'est rattachée à ce compte.")
    return professeur


class PropositionListView(TeacherRoleRequiredMixin, TemplateView):
    template_name = "enseignant/propositions.html"

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        professeur = _fiche_du_compte(self.request.user)
        propositions = PropositionEnseignement.objects.filter(professeur=professeur).select_related(
            "cours_session__cours__discipline",
            "cours_session__session",
            "proposee_par",
        )
        contexte.update(
            {
                "nav": "propositions",
                "professeur": professeur,
                "en_attente": [p for p in propositions if p.est_en_attente],
                "traitees": [p for p in propositions if not p.est_en_attente][:20],
            }
        )
        return contexte


class PropositionReponseView(TeacherRoleRequiredMixin, View):
    """Accepter, ou décliner avec un motif.

    La proposition est relue depuis la fiche de l'enseignant, jamais depuis son
    seul identifiant : sans cela, un numéro deviné suffirait à répondre à la
    place d'un collègue.
    """

    http_method_names = ["post"]

    def post(self, request, pk):
        professeur = _fiche_du_compte(request.user)
        proposition = get_object_or_404(
            PropositionEnseignement.objects.select_related("cours_session__cours"),
            pk=pk,
            professeur=professeur,
        )
        intitule = proposition.cours_session.cours.titre

        try:
            if request.POST.get("action") == "accepter":
                proposition.accepter()
                messages.success(request, f"« {intitule} » vous est désormais affecté.")
            else:
                proposition.decliner(request.POST.get("motif", ""))
                messages.success(request, "Proposition déclinée : l'administration en est informée.")
        except ValidationError as erreur:
            messages.error(request, erreur.messages[0])
            return redirect("enseignant:propositions")

        if proposition.proposee_par_id:
            notifier(
                proposition.proposee_par,
                f"Proposition {proposition.get_statut_display().lower()} — {intitule}",
                type_notification=Notification.Type.SYSTEME,
                # Le motif reste dans le message : c'est la seule chose qui
                # explique un refus, et les précisions ne partent qu'au courriel.
                message=(
                    f"{professeur.nom_complet} a {proposition.get_statut_display().lower()} "
                    f"la proposition d'enseigner « {intitule} »."
                    + (f" Motif : {proposition.motif_refus}." if proposition.motif_refus else "")
                ),
                details=[
                    {"libelle": "Enseignant", "valeur": professeur.nom_complet},
                    {"libelle": "Cours", "valeur": intitule},
                    {"libelle": "Réponse", "valeur": proposition.get_statut_display()},
                ],
                url_cible=reverse("administration:professeur_detail", kwargs={"pk": professeur.pk}),
            )
        return redirect("enseignant:propositions")
