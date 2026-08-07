"""Écrire et publier une actualité depuis le back-office.

Les actualités restent des pages Wagtail pour leur URL, leur publication et
leur place dans l'arbre. Leur corps structuré vit dans un modèle associé : cela
permet de conserver sans conversion destructive le RichText historique des
anciennes actualités.
"""

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.utils.html import escape
from django.utils.text import slugify
from django.views import View
from django.views.generic import ListView, TemplateView
from wagtail.actions.unpublish_page import UnpublishPageAction
from wagtail.coreutils import find_available_slug
from wagtail.images import get_image_model

from apps.core.mixins import StaffRoleRequiredMixin
from apps.core.models import JournalAudit
from apps.core.services.audit import journaliser
from apps.core.services.redaction import en_texte
from apps.website.formulaires_actualites import ActualiteForm
from apps.website.models import NewsIndexPage, NewsPage
from apps.website.models_publications import ContenuActualite


def _index_des_actualites() -> NewsIndexPage:
    index = NewsIndexPage.objects.first()
    if index is None:
        raise Http404(
            "Aucune page « Actualités » n'existe encore dans l'arborescence du site. "
            "Lancez « python manage.py setup_initial_pages » pour la créer."
        )
    return index


def _publier(actualite, utilisateur):
    actualite.save_revision(user=utilisateur).publish(user=utilisateur, skip_permission_checks=True)


def _depublier(actualite, utilisateur):
    UnpublishPageAction(actualite, user=utilisateur).execute(skip_permission_checks=True)


def _texte_pour_meta(contenu) -> str:
    """Extrait un texte lisible sans essayer de sérialiser les blocs complexes."""
    for bloc in contenu or []:
        if bloc.block_type == "texte":
            return en_texte(str(bloc.value), limite=300)
        valeur = bloc.value
        if hasattr(valeur, "get"):
            titre = valeur.get("titre")
            if titre:
                return str(titre)[:300]
    return ""


def _corps_compatibilite(contenu, *, historique: str = "", chapeau: str = "", titre: str = "") -> str:
    """Maintient le champ RichText Wagtail obligatoire sans dupliquer l'éditeur.

    Le rendu public privilégie ``ContenuActualite``. ``NewsPage.body`` reste
    néanmoins requis par Wagtail lors de ``save_revision`` et sert aussi de
    filet de sécurité pour les anciennes actualités. Quand un bloc texte existe,
    il devient ce repli ; sinon un corps historique déjà présent est conservé.
    Une actualité neuve composée uniquement de blocs structurés reçoit enfin un
    court paragraphe issu du chapeau ou du titre afin de rester valide.
    """
    for bloc in contenu or []:
        if bloc.block_type == "texte":
            texte = str(bloc.value).strip()
            if texte:
                return texte

    if historique and historique.strip():
        return historique

    repli = en_texte(chapeau or titre, limite=500).strip() or "Actualité ITEAG"
    return f"<p>{escape(repli)}</p>"


class ActualitesGestionView(StaffRoleRequiredMixin, ListView):
    template_name = "website/actualites/gestion.html"
    context_object_name = "actualites"
    paginate_by = 25

    def get_queryset(self):
        return NewsPage.objects.order_by("-date", "-id")

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        contexte["nav"] = "actualites"
        contexte["brouillons"] = [a for a in contexte["actualites"] if not a.live]
        contexte["en_ligne"] = [a for a in contexte["actualites"] if a.live]
        return contexte


class ActualiteEditionView(StaffRoleRequiredMixin, TemplateView):
    template_name = "website/actualites/formulaire.html"

    def _actualite(self):
        if "pk" not in self.kwargs:
            return None
        return get_object_or_404(NewsPage, pk=self.kwargs["pk"])

    @staticmethod
    def _contenu_initial(actualite):
        if actualite is None:
            return []
        try:
            return actualite.contenu_structure.contenu
        except ContenuActualite.DoesNotExist:
            if not actualite.body:
                return []
            stream_block = ContenuActualite._meta.get_field("contenu").stream_block
            return stream_block.to_python([{"type": "texte", "value": actualite.body}])

    def _valeurs_initiales(self, actualite):
        if actualite is None:
            return {}
        return {
            "titre": actualite.title,
            "date": actualite.date,
            "chapeau": actualite.excerpt,
            "contenu": self._contenu_initial(actualite),
        }

    def get_context_data(self, **kwargs):
        actualite = self._actualite()
        return {
            **super().get_context_data(**kwargs),
            "nav": "actualites",
            "actualite": actualite,
            "form": kwargs.get("form") or ActualiteForm(initial=self._valeurs_initiales(actualite)),
        }

    def post(self, request, *args, **kwargs):
        actualite = self._actualite()
        formulaire = ActualiteForm(request.POST, request.FILES)
        if not formulaire.is_valid():
            return self.render_to_response(self.get_context_data(form=formulaire))

        donnees = formulaire.cleaned_data
        creation = actualite is None
        index = _index_des_actualites() if creation else None
        corps_historique = "" if creation else actualite.body

        if creation:
            actualite = NewsPage(
                title=donnees["titre"],
                slug=find_available_slug(index, slugify(donnees["titre"]) or "actualite"),
                live=False,
                has_unpublished_changes=True,
            )
        else:
            actualite.title = donnees["titre"]

        actualite.date = donnees["date"]
        actualite.excerpt = donnees["chapeau"]
        actualite.body = _corps_compatibilite(
            donnees["contenu"],
            historique=corps_historique,
            chapeau=donnees["chapeau"],
            titre=donnees["titre"],
        )
        actualite.meta_description = en_texte(
            donnees["chapeau"] or _texte_pour_meta(donnees["contenu"]) or donnees["titre"],
            limite=300,
        )

        if donnees.get("image"):
            actualite.image = self._image_wagtail(donnees["image"], donnees["titre"], request.user)

        if creation:
            index.add_child(instance=actualite)
        else:
            actualite.save()

        ContenuActualite.objects.update_or_create(
            actualite=actualite,
            defaults={"contenu": donnees["contenu"]},
        )

        if actualite.live:
            _publier(actualite, request.user)
        else:
            actualite.save_revision(user=request.user)

        journaliser(
            JournalAudit.Action.CREATION if creation else JournalAudit.Action.MODIFICATION,
            utilisateur=request.user,
            request=request,
            objet=actualite,
            objet_libelle=f"Actualité « {actualite.title} »",
        )
        messages.success(
            request,
            "Actualité enregistrée. Elle reste hors ligne tant que vous ne l'avez pas publiée."
            if not actualite.live
            else "Actualité mise à jour — la page en ligne est à jour.",
        )
        return redirect("website:actualite_edition", pk=actualite.pk)

    @staticmethod
    def _image_wagtail(fichier, titre: str, utilisateur):
        Image = get_image_model()
        return Image.objects.create(
            title=titre[:255],
            file=fichier,
            uploaded_by_user=utilisateur if utilisateur.is_authenticated else None,
        )


class ActualiteDecisionView(StaffRoleRequiredMixin, View):
    http_method_names = ["post"]

    def post(self, request, pk):
        actualite = get_object_or_404(NewsPage, pk=pk)
        action = request.POST.get("action")
        titre = actualite.title

        try:
            if action == "publier":
                _publier(actualite, request.user)
                trace, avis = JournalAudit.Action.CHANGEMENT_STATUT, f"« {titre} » est en ligne."
            elif action == "depublier":
                _depublier(actualite, request.user)
                trace, avis = JournalAudit.Action.CHANGEMENT_STATUT, f"« {titre} » est retirée du site."
            elif action == "supprimer":
                trace, avis = JournalAudit.Action.SUPPRESSION, f"« {titre} » a été supprimée."
            else:
                raise ValidationError("Action inconnue.")
        except ValidationError as erreur:
            messages.error(request, erreur.messages[0])
            return redirect("website:actualites_gestion")

        if action == "supprimer":
            identifiant = str(actualite.pk)
            actualite.delete()
            journaliser(
                trace,
                utilisateur=request.user,
                request=request,
                objet_type="NewsPage",
                objet_id=identifiant,
                objet_libelle=f"Actualité « {titre} »",
            )
        else:
            journaliser(
                trace,
                utilisateur=request.user,
                request=request,
                objet=actualite,
                objet_libelle=f"Actualité « {titre} » → {'en ligne' if actualite.live else 'hors ligne'}",
            )

        messages.success(request, avis)
        return redirect("website:actualites_gestion")
