from django.db.models import Q
from django.views.generic import DetailView, ListView

from apps.formations.models import Discipline
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
            qs = qs.filter(
                Q(titre__icontains=q)
                | Q(auteur__icontains=q)
                | Q(mots_cles__icontains=q)
                | Q(cote__icontains=q)
            )
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
