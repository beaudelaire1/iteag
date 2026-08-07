from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views import View
from django.views.generic import ListView

from apps.core.mixins import AdminRoleRequiredMixin
from apps.core.models import JournalAudit
from apps.core.services.audit import journaliser
from apps.website.models_publications import TemoignageEtudiant


class TemoignageListView(AdminRoleRequiredMixin, ListView):
    template_name = "administration/temoignages.html"
    context_object_name = "temoignages"
    paginate_by = 30

    def get_queryset(self):
        return TemoignageEtudiant.objects.select_related("etudiant", "valide_par").order_by(
            "statut", "-soumis_le"
        )

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        base = TemoignageEtudiant.objects.all()
        contexte.update(
            {
                "nav": "temoignages",
                "en_attente": base.filter(statut=TemoignageEtudiant.Statut.EN_ATTENTE).count(),
                "publies": base.filter(statut=TemoignageEtudiant.Statut.PUBLIE).count(),
                "refuses": base.filter(statut=TemoignageEtudiant.Statut.REFUSE).count(),
            }
        )
        return contexte


class TemoignageDecisionView(AdminRoleRequiredMixin, View):
    http_method_names = ["post"]

    def post(self, request, pk):
        temoignage = get_object_or_404(TemoignageEtudiant, pk=pk)
        action = request.POST.get("action")

        if action == "publier":
            if not temoignage.consentement_publication:
                messages.error(request, "Ce témoignage ne peut pas être publié sans consentement explicite.")
                return redirect("administration:temoignages")
            temoignage.statut = TemoignageEtudiant.Statut.PUBLIE
            temoignage.motif_refus = ""
            temoignage.valide_le = timezone.now()
            temoignage.valide_par = request.user
            avis = f"Le témoignage de {temoignage.nom_affiche} est publié."
        elif action == "refuser":
            motif = (request.POST.get("motif") or "").strip()
            if not motif:
                messages.error(request, "Indiquez le motif du refus pour que l'étudiant puisse corriger son texte.")
                return redirect("administration:temoignages")
            temoignage.statut = TemoignageEtudiant.Statut.REFUSE
            temoignage.motif_refus = motif
            temoignage.valide_le = None
            temoignage.valide_par = request.user
            avis = f"Le témoignage de {temoignage.nom_affiche} a été refusé."
        else:
            messages.error(request, "Action inconnue.")
            return redirect("administration:temoignages")

        temoignage.save(update_fields=["statut", "motif_refus", "valide_le", "valide_par", "modifie_le"])
        journaliser(
            JournalAudit.Action.CHANGEMENT_STATUT,
            utilisateur=request.user,
            request=request,
            objet=temoignage,
            objet_libelle=f"Témoignage « {temoignage.nom_affiche} » → {temoignage.get_statut_display()}",
        )
        messages.success(request, avis)
        return redirect("administration:temoignages")
