from django.contrib import messages
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views import View
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from apps.core.mixins import AdminRoleRequiredMixin, StaffRoleRequiredMixin
from apps.formations.models import Discipline
from apps.library.formulaires import NoticeForm

from .models import NoticeBibliographique


class CatalogueView(ListView):
    """Catalogue public de la bibliothèque — BIB-001/BIB-002."""

    model = NoticeBibliographique
    template_name = "library/catalogue.html"
    context_object_name = "notices"
    paginate_by = 20

    def get_template_names(self):
        if self.request.headers.get("HX-Request"):
            return ["library/partials/results.html"]
        return [self.template_name]

    def get_queryset(self):
        qs = super().get_queryset().select_related("discipline")
        q = self.request.GET.get("q", "").strip()
        discipline = self.request.GET.get("discipline", "").strip()
        author = self.request.GET.get("author", "").strip()
        year = self.request.GET.get("year", "").strip()
        ordering = self.request.GET.get("sort", "titre")

        if q:
            qs = self._apply_search(qs, q)
        if discipline:
            qs = qs.filter(discipline__slug=discipline)
        if author:
            qs = qs.filter(auteur__icontains=author)
        if year:
            qs = qs.filter(date_publication__icontains=year)

        if ordering == "auteur":
            qs = qs.order_by("auteur", "titre")
        elif ordering == "recent":
            qs = qs.order_by("-date_publication", "titre")
        elif ordering == "pertinence" and q:
            pass  # Déjà trié par rank dans _apply_search

        return qs

    def _apply_search(self, qs, q):
        """Full-text PostgreSQL, doublé d'un « contient » qui ne dépend pas de l'index.

        Le vecteur n'est calculé qu'au `save()` : une notice importée en masse
        reste invisible au plein texte seul. Et une cote comme « TP-222 » ne
        survit pas toujours à l'analyse lexicale. Les deux voies sont donc
        réunies plutôt qu'opposées.
        """
        from django.db import connection

        litteral = Q(titre__icontains=q) | Q(auteur__icontains=q) | Q(cote__icontains=q) | Q(isbn__icontains=q)

        if connection.vendor == "postgresql":
            from django.contrib.postgres.search import SearchQuery, SearchRank

            search_query = SearchQuery(q, config="french")
            qs = (
                qs.filter(Q(search_vector=search_query) | litteral)
                .annotate(rank=SearchRank("search_vector", search_query))
                .order_by("-rank", "titre")
            )
        else:
            qs = qs.filter(litteral | Q(mots_cles__icontains=q))
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["query"] = self.request.GET.get("q", "")
        context["current_discipline"] = self.request.GET.get("discipline", "")
        context["current_author"] = self.request.GET.get("author", "")
        context["current_year"] = self.request.GET.get("year", "")
        context["current_sort"] = self.request.GET.get("sort", "titre")
        context["disciplines"] = Discipline.objects.filter(notices__isnull=False).distinct().order_by("nom")
        return context


class NoticeDetailView(DetailView):
    model = NoticeBibliographique
    template_name = "library/notice_detail.html"
    context_object_name = "notice"


# ══════════════════════════════════════════════
# Back-office — gestion des notices
# ══════════════════════════════════════════════
#
# La bibliothèque n'avait aucun écran de gestion : le catalogue se consultait
# mais ne s'administrait que par l'interface Django. Or tenir le fonds fait
# partie du travail courant du secrétariat, au même titre que la boutique.


class GestionNoticesView(StaffRoleRequiredMixin, ListView):
    """Fonds documentaire, avec recherche et état de disponibilité."""

    model = NoticeBibliographique
    template_name = "library/gestion.html"
    context_object_name = "notices"
    paginate_by = 25

    def get_queryset(self):
        queryset = NoticeBibliographique.objects.select_related("discipline").order_by("cote", "titre")
        recherche = self.request.GET.get("q", "").strip()
        discipline = self.request.GET.get("discipline", "").strip()
        disponibilite = self.request.GET.get("disponible", "").strip()

        if recherche:
            queryset = queryset.filter(
                Q(titre__icontains=recherche)
                | Q(auteur__icontains=recherche)
                | Q(cote__icontains=recherche)
                | Q(isbn__icontains=recherche)
            )
        if discipline:
            queryset = queryset.filter(discipline_id=discipline)
        if disponibilite in ("oui", "non"):
            queryset = queryset.filter(disponible=disponibilite == "oui")
        return queryset

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        fonds = NoticeBibliographique.objects.all()
        contexte.update(
            {
                "disciplines": Discipline.objects.order_by("ordre", "nom"),
                "query": self.request.GET.get("q", ""),
                "current_discipline": self.request.GET.get("discipline", ""),
                "current_disponible": self.request.GET.get("disponible", ""),
                "total_fonds": fonds.count(),
                "total_sorties": fonds.filter(disponible=False).count(),
                "total_sans_cote": fonds.filter(cote="").count(),
            }
        )
        return contexte


class NoticeCreateView(StaffRoleRequiredMixin, CreateView):
    model = NoticeBibliographique
    form_class = NoticeForm
    template_name = "administration/form.html"

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        contexte.update(
            {
                "form_title": "Nouvelle notice",
                "nav": "bibliotheque",
                "cancel_url": reverse("library:gestion"),
            }
        )
        return contexte

    def form_valid(self, form):
        messages.success(self.request, f"Notice « {form.instance.titre} » ajoutée au fonds.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("library:gestion")


class NoticeUpdateView(StaffRoleRequiredMixin, UpdateView):
    model = NoticeBibliographique
    form_class = NoticeForm
    template_name = "administration/form.html"

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        contexte.update(
            {
                "form_title": f"Modifier « {self.object.titre} »",
                "nav": "bibliotheque",
                "cancel_url": reverse("library:gestion"),
            }
        )
        return contexte

    def form_valid(self, form):
        messages.success(self.request, "Notice mise à jour.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("library:gestion")


class NoticeDisponibiliteView(StaffRoleRequiredMixin, View):
    """Bascule « en rayon / sorti » en un clic.

    Le geste le plus fréquent du fonds mérite de ne pas passer par un
    formulaire complet : c'est un prêt ou un retour, pas une correction de
    notice.
    """

    http_method_names = ["post"]

    def post(self, request, pk):
        notice = get_object_or_404(NoticeBibliographique, pk=pk)
        notice.disponible = not notice.disponible
        notice.save(update_fields=["disponible", "updated_at"])
        etat = "de retour en rayon" if notice.disponible else "sortie du fonds"
        messages.success(request, f"« {notice.titre} » {etat}.")
        return redirect(request.META.get("HTTP_REFERER") or reverse("library:gestion"))


class NoticeDeleteView(AdminRoleRequiredMixin, DeleteView):
    """Retrait définitif — réservé à la direction, comme toute suppression."""

    model = NoticeBibliographique
    template_name = "administration/confirm_delete.html"

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        contexte.update(
            {
                "objet": self.object,
                "titre": "Retirer cette notice du fonds",
                "cancel_url": reverse("library:gestion"),
                "nav": "bibliotheque",
            }
        )
        return contexte

    def get_success_url(self):
        messages.success(self.request, "Notice retirée du fonds.")
        return reverse("library:gestion")
