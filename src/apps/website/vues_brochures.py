"""Brochures : dépôt par le secrétariat, consultation par le public.

Le cycle est volontairement plus court que celui des actualités. Une brochure
n'a pas de corps à composer ni de page à créer dans l'arborescence : elle est
déposée, relue, publiée. Ce qui compte est qu'un brouillon ne soit lisible de
personne — y compris par l'adresse directe de son fichier.
"""

from django.contrib import messages
from django.db.models import F, Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import ListView, TemplateView

from apps.core.mixins import StaffRoleRequiredMixin
from apps.core.models import JournalAudit
from apps.core.services.audit import journaliser
from apps.website.formulaires_brochures import BrochureForm
from apps.website.models_publications import Brochure

# ══════════════════════════════════════════════
# Gestion — secrétariat et direction
# ══════════════════════════════════════════════


class BrochuresGestionView(StaffRoleRequiredMixin, ListView):
    template_name = "website/brochures/gestion.html"
    context_object_name = "brochures"
    paginate_by = 30

    def get_queryset(self):
        return Brochure.objects.select_related("deposee_par")

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        brochures = contexte["brochures"]
        contexte.update(
            {
                "nav": "brochures",
                "brouillons": [b for b in brochures if not b.est_publiee],
                "en_ligne": [b for b in brochures if b.est_publiee],
            }
        )
        return contexte


class BrochureEditionView(StaffRoleRequiredMixin, TemplateView):
    """Dépôt d'une nouvelle brochure ou correction d'une existante."""

    template_name = "website/brochures/formulaire.html"

    def _brochure(self):
        if "pk" not in self.kwargs:
            return None
        return get_object_or_404(Brochure, pk=self.kwargs["pk"])

    def get_context_data(self, **kwargs):
        brochure = self._brochure()
        return {
            **super().get_context_data(**kwargs),
            "nav": "brochures",
            "brochure": brochure,
            "form": kwargs.get("form") or BrochureForm(instance=brochure),
        }

    def post(self, request, *args, **kwargs):
        brochure = self._brochure()
        formulaire = BrochureForm(request.POST, request.FILES, instance=brochure)
        if not formulaire.is_valid():
            return self.render_to_response(self.get_context_data(form=formulaire))

        enregistree = formulaire.save(commit=False)
        if brochure is None:
            enregistree.deposee_par = request.user
        enregistree.save()

        journaliser(
            JournalAudit.Action.CREATION if brochure is None else JournalAudit.Action.MODIFICATION,
            request=request,
            objet=enregistree,
            objet_libelle=f"Brochure « {enregistree.titre} »",
        )
        messages.success(
            request,
            "Brochure enregistrée. Elle reste hors ligne tant que vous ne l'avez pas publiée."
            if not enregistree.est_publiee
            else "Brochure mise à jour ; la version en ligne est remplacée.",
        )
        return redirect("website:brochures_gestion")


class BrochureDecisionView(StaffRoleRequiredMixin, View):
    """Publier, retirer ou supprimer une brochure."""

    http_method_names = ["post"]

    def post(self, request, pk):
        brochure = get_object_or_404(Brochure, pk=pk)
        action = request.POST.get("action")
        titre = brochure.titre

        if action == "publier":
            brochure.publier()
            journaliser(
                JournalAudit.Action.CHANGEMENT_STATUT,
                request=request,
                objet=brochure,
                objet_libelle=f"Brochure « {titre} » → en ligne",
            )
            messages.success(request, f"« {titre} » est en ligne sur la page Brochures.")
        elif action == "depublier":
            brochure.depublier()
            journaliser(
                JournalAudit.Action.CHANGEMENT_STATUT,
                request=request,
                objet=brochure,
                objet_libelle=f"Brochure « {titre} » → hors ligne",
            )
            messages.success(request, f"« {titre} » est retirée du site. Le fichier reste conservé.")
        elif action == "supprimer":
            identifiant = str(brochure.pk)
            # Le fichier part avec la fiche : le garder produirait un média
            # orphelin que plus rien ne référence et que personne ne nettoiera.
            if brochure.fichier:
                brochure.fichier.delete(save=False)
            if brochure.couverture:
                brochure.couverture.delete(save=False)
            brochure.delete()
            journaliser(
                JournalAudit.Action.SUPPRESSION,
                request=request,
                objet_type="Brochure",
                objet_id=identifiant,
                objet_libelle=f"Brochure « {titre} »",
            )
            messages.success(request, f"« {titre} » a été supprimée.")
        else:
            messages.error(request, "Action inconnue.")

        return redirect("website:brochures_gestion")


# ══════════════════════════════════════════════
# Lecture publique
# ══════════════════════════════════════════════


class BrochuresPubliquesView(ListView):
    template_name = "website/brochures/liste_publique.html"
    context_object_name = "brochures"
    paginate_by = 24

    def get_queryset(self):
        requete = Brochure.objects.filter(statut=Brochure.Statut.PUBLIEE)
        categorie = self.request.GET.get("categorie", "").strip()
        if categorie in Brochure.Categorie.values:
            requete = requete.filter(categorie=categorie)
        recherche = self.request.GET.get("q", "").strip()
        if recherche:
            requete = requete.filter(Q(titre__icontains=recherche) | Q(description__icontains=recherche))
        return requete

    def get_context_data(self, **kwargs):
        return {
            **super().get_context_data(**kwargs),
            "recherche": self.request.GET.get("q", ""),
            "categorie_active": self.request.GET.get("categorie", ""),
            "categories": Brochure.Categorie.choices,
        }


class BrochureTelechargementView(View):
    """Sert le PDF d'une brochure publiée, et compte le téléchargement.

    Le fichier passe par cette vue plutôt que par son adresse de média : c'est
    le seul moyen de garantir qu'un brouillon reste invisible même si son
    chemin de stockage est deviné, et d'obtenir un décompte fiable.
    """

    http_method_names = ["get", "head"]

    def get(self, request, slug):
        brochure = get_object_or_404(Brochure, slug=slug, statut=Brochure.Statut.PUBLIEE)
        if not brochure.fichier:
            raise Http404("Le fichier de cette brochure est introuvable.")

        # Une écriture atomique plutôt qu'un « save » : deux visiteurs
        # simultanés perdraient sinon l'un des deux passages.
        Brochure.objects.filter(pk=brochure.pk).update(nombre_telechargements=F("nombre_telechargements") + 1)

        try:
            fichier = brochure.fichier.open("rb")
        except (FileNotFoundError, OSError) as erreur:
            raise Http404("Le fichier de cette brochure est introuvable.") from erreur

        # Le nom porte le titre de la brochure, pas le chemin de stockage :
        # c'est ce que le visiteur retrouvera dans son dossier de
        # téléchargements, et « brochure-institutionnelle-2026.pdf » s'y relit
        # mieux qu'un nom horodaté.
        nom = f"{brochure.slug}{brochure.extension}"
        return FileResponse(fichier, content_type=brochure.type_mime, as_attachment=False, filename=nom)
