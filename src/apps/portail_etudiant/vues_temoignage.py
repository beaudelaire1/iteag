from django.contrib import messages
from django.shortcuts import redirect
from django.views.generic import TemplateView

from apps.core.mixins import StudentRoleRequiredMixin
from apps.portail_etudiant.formulaires_temoignage import TemoignageEtudiantForm
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
        # Toute modification repasse devant la direction, y compris après une
        # publication : un texte validé ne peut jamais être changé en public
        # sans nouvelle validation.
        temoignage.statut = TemoignageEtudiant.Statut.EN_ATTENTE
        temoignage.motif_refus = ""
        temoignage.valide_le = None
        temoignage.valide_par = None
        temoignage.save()

        messages.success(request, "Votre témoignage a été transmis à la direction pour validation.")
        return redirect("etudiant:temoignage")
