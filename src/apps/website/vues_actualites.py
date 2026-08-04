"""Écrire et publier une actualité depuis le back-office.

Les actualités sont des pages Wagtail, et n'étaient donc rédigeables que dans
l'administration Wagtail — à laquelle ni le secrétariat ni la direction n'ont
de chemin depuis leur espace. Annoncer une rentrée, une soutenance ou une
journée portes ouvertes supposait de connaître une seconde interface, ses
notions d'arbre, de révision et de brouillon. Autant dire que personne ne
publiait.

Ce module donne l'acte, pas l'outil : écrire, publier, dépublier, supprimer.
Le reste — l'arborescence, les révisions, la médiathèque — reste dans Wagtail
pour qui en a l'usage.

**Ce que Wagtail impose et qu'on ne peut pas simplifier.** Une page n'est pas
un enregistrement ordinaire :

- elle vit dans un arbre : elle s'insère sous son index par « add_child », et
  une page enregistrée hors de l'arbre n'a ni URL ni existence publique ;
- son adresse doit être unique sous son parent : le fragment d'URL est calculé
  à la création, puis **ne bouge plus**. Le titre peut être corrigé sans que
  les liens déjà partagés se brisent ;
- « en ligne » et « enregistré » sont deux états distincts : une actualité
  s'écrit en brouillon, se relit, et ne paraît qu'à la publication.
"""

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.utils.text import slugify
from django.views import View
from django.views.generic import ListView, TemplateView
from wagtail.actions.unpublish_page import UnpublishPageAction
from wagtail.coreutils import find_available_slug
from wagtail.images import get_image_model

from apps.core.mixins import StaffRoleRequiredMixin
from apps.core.models import JournalAudit
from apps.core.services.audit import journaliser
from apps.core.services.redaction import assainir, en_texte
from apps.website.formulaires_actualites import ActualiteForm
from apps.website.models import NewsIndexPage, NewsPage


def _index_des_actualites() -> NewsIndexPage:
    """La page sous laquelle les actualités s'insèrent.

    Elle est créée par « setup_initial_pages ». Son absence n'est pas une
    erreur d'utilisateur mais un site non initialisé : le dire franchement vaut
    mieux qu'une exception de clé étrangère trois appels plus loin.
    """
    index = NewsIndexPage.objects.first()
    if index is None:
        raise Http404(
            "Aucune page « Actualités » n'existe encore dans l'arborescence du site. "
            "Lancez « python manage.py setup_initial_pages » pour la créer."
        )
    return index


# Wagtail porte son propre système de droits — groupes et permissions posées
# sur une branche de l'arbre — que ce projet n'emploie pas : personne n'est
# inscrit dans un groupe Wagtail, donc « can_publish() » est faux pour tout le
# monde, direction comprise. L'autorisation est décidée à la porte, par le
# « StaffRoleRequiredMixin ». « skip_permission_checks » dit exactement cela ;
# « user » reste transmis pour que le journal de Wagtail sache qui a agi.


def _publier(actualite, utilisateur):
    actualite.save_revision(user=utilisateur).publish(user=utilisateur, skip_permission_checks=True)


def _depublier(actualite, utilisateur):
    UnpublishPageAction(actualite, user=utilisateur).execute(skip_permission_checks=True)


class ActualitesGestionView(StaffRoleRequiredMixin, ListView):
    """La liste, brouillons compris — c'est tout l'intérêt de l'écran."""

    template_name = "website/actualites/gestion.html"
    context_object_name = "actualites"
    paginate_by = 25

    def get_queryset(self):
        # « NewsPage.objects » retourne aussi les brouillons ; « live() » les
        # écarterait, et l'on ne verrait jamais ce qu'on est en train d'écrire.
        return NewsPage.objects.order_by("-date", "-id")

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        contexte["nav"] = "actualites"
        contexte["brouillons"] = [a for a in contexte["actualites"] if not a.live]
        contexte["en_ligne"] = [a for a in contexte["actualites"] if a.live]
        return contexte


class ActualiteEditionView(StaffRoleRequiredMixin, TemplateView):
    """Création et correction, sur le même écran.

    Une actualité en ligne reste corrigeable — contrairement à un article de
    recherche, qui doit repasser par la relecture. Une annonce se corrige au
    fil de l'eau : une date d'examen erronée doit pouvoir être rectifiée dans
    la minute, et personne d'autre n'a à en juger.
    """

    template_name = "website/actualites/formulaire.html"

    def _actualite(self):
        if "pk" not in self.kwargs:
            return None
        return get_object_or_404(NewsPage, pk=self.kwargs["pk"])

    def _valeurs_initiales(self, actualite):
        if actualite is None:
            return {}
        return {
            "titre": actualite.title,
            "date": actualite.date,
            "chapeau": actualite.excerpt,
            "corps": actualite.body,
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
        corps = assainir(donnees["corps"])
        creation = actualite is None
        index = _index_des_actualites() if creation else None

        if creation:
            actualite = NewsPage(
                title=donnees["titre"],
                # Calculé une fois, à la création : le titre peut ensuite être
                # corrigé sans casser les liens déjà partagés.
                slug=find_available_slug(index, slugify(donnees["titre"]) or "actualite"),
                # Une annonce s'écrit avant de paraître. Elle naît donc hors
                # ligne, et la publication est un second geste, explicite.
                live=False,
                has_unpublished_changes=True,
            )
        else:
            actualite.title = donnees["titre"]

        actualite.date = donnees["date"]
        actualite.excerpt = donnees["chapeau"]
        actualite.body = corps
        actualite.meta_description = en_texte(donnees["chapeau"] or corps, limite=300)

        if donnees.get("image"):
            actualite.image = self._image_wagtail(donnees["image"], donnees["titre"], request.user)

        if creation:
            index.add_child(instance=actualite)
        else:
            actualite.save()

        # Une actualité déjà en ligne reste en ligne : sans cette publication,
        # la correction ne vivrait que dans la révision et le visiteur
        # continuerait de lire l'ancienne version.
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
        """Verse l'image dans la médiathèque Wagtail.

        Le champ du modèle pointe vers « wagtailimages.Image » : un fichier
        seul n'y entre pas. Largeur et hauteur sont renseignées par Django à
        l'affectation du fichier, l'« ImageField » de Wagtail déclarant
        « width_field » et « height_field ».
        """
        Image = get_image_model()
        return Image.objects.create(
            title=titre[:255],
            file=fichier,
            uploaded_by_user=utilisateur if utilisateur.is_authenticated else None,
        )


class ActualiteDecisionView(StaffRoleRequiredMixin, View):
    """Publier, dépublier, supprimer."""

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
                # Dépublier, et non supprimer : le texte reste, l'adresse cesse
                # de répondre. Une annonce périmée se remet en ligne l'année
                # suivante à peu de frais.
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
