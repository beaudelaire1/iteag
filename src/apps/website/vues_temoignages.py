from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views import View
from django.views.generic import ListView, TemplateView

from apps.core.mixins import AdminRoleRequiredMixin, StudentRoleRequiredMixin
from apps.core.models import JournalAudit
from apps.core.services.audit import journaliser
from apps.website.formulaires_temoignages import TemoignageEtudiantForm
from apps.website.models_publications import TemoignageEtudiant


class TemoignageEtudiantView(StudentRoleRequiredMixin, TemplateView):
    template_name = "etudiant/temoignage.html"

    def _temoignage(self):
        return TemoignageEtudiant.objects.filter(etudiant=self.request.user).first()

    def _promotion(self):
        profil = self.request.user.profil_etudiant
        if profil.promotion_id:
            return str(profil.promotion)
        if profil.parcours_id:
            return str(profil.parcours)
        return "Étudiant ITEAG"

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        temoignage = self._temoignage()
        contexte.update(
            {
                "nav": "temoignage",
                "temoignage": temoignage,
                "form": kwargs.get("form")
                or TemoignageEtudiantForm(
                    initial={
                        "texte": temoignage.texte if temoignage else "",
                        "consentement_publication": temoignage.consentement_publication if temoignage else False,
                    }
                ),
            }
        )
        return contexte

    def post(self, request, *args, **kwargs):
        formulaire = TemoignageEtudiantForm(request.POST)
        if not formulaire.is_valid():
            return self.render_to_response(self.get_context_data(form=formulaire))

        nom = request.user.get_full_name().strip() or request.user.username
        temoignage, _ = TemoignageEtudiant.objects.get_or_create(
            etudiant=request.user,
            defaults={"nom_affiche": nom, "promotion": self._promotion()},
        )
        temoignage.nom_affiche = nom
        temoignage.promotion = self._promotion()
        temoignage.texte = formulaire.cleaned_data["texte"]
        temoignage.consentement_publication = formulaire.cleaned_data["consentement_publication"]
        # Toute modification repasse devant la direction : une version publiée
        # ne peut jamais être modifiée publiquement sans nouvelle validation.
        temoignage.statut = TemoignageEtudiant.Statut.EN_ATTENTE
        temoignage.motif_refus = ""
        temoignage.valide_le = None
        temoignage.valide_par = None
        temoignage.save()

        messages.success(request, "Votre témoignage a été transmis à la direction pour validation.")
        return redirect("website:temoignage_etudiant")


class TemoignageListView(AdminRoleRequiredMixin, ListView):
    template_name = "administration/temoignages.html"
    context_object_name = "temoignages"

    def get_queryset(self):
        return TemoignageEtudiant.objects.select_related("etudiant", "valide_par").order_by("statut", "-soumis_le")

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

    def post(self, request):
        temoignage = get_object_or_404(TemoignageEtudiant, pk=request.POST.get("temoignage_id"))
        action = request.POST.get("action")

        if action == "publier":
            if not temoignage.consentement_publication:
                messages.error(request, "Ce témoignage ne peut pas être publié sans consentement explicite.")
                return redirect("website:temoignages_gestion")
            temoignage.statut = TemoignageEtudiant.Statut.PUBLIE
            temoignage.motif_refus = ""
            temoignage.valide_le = timezone.now()
            temoignage.valide_par = request.user
            avis = f"Le témoignage de {temoignage.nom_affiche} est publié."
        elif action == "refuser":
            motif = (request.POST.get("motif") or "").strip()
            if not motif:
                messages.error(request, "Indiquez le motif du refus pour que l'étudiant puisse corriger son texte.")
                return redirect("website:temoignages_gestion")
            temoignage.statut = TemoignageEtudiant.Statut.REFUSE
            temoignage.motif_refus = motif
            temoignage.valide_le = None
            temoignage.valide_par = request.user
            avis = f"Le témoignage de {temoignage.nom_affiche} a été refusé."
        else:
            messages.error(request, "Action inconnue.")
            return redirect("website:temoignages_gestion")

        temoignage.save(update_fields=["statut", "motif_refus", "valide_le", "valide_par", "modifie_le"])
        journaliser(
            JournalAudit.Action.CHANGEMENT_STATUT,
            utilisateur=request.user,
            request=request,
            objet=temoignage,
            objet_libelle=f"Témoignage « {temoignage.nom_affiche} » → {temoignage.get_statut_display()}",
        )
        messages.success(request, avis)
        return redirect("website:temoignages_gestion")
