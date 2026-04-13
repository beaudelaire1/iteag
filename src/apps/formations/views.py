from django.db.models import Q
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from django.views.generic import DetailView, ListView

from .models import Cours, Discipline, Parcours, Professeur, Tarif


@method_decorator(cache_page(300), name="dispatch")  # 5 min
class ParcoursListView(ListView):
    model = Parcours
    template_name = "formations/parcours_list.html"
    context_object_name = "parcours_list"
    paginate_by = 8

    def get_queryset(self):
        queryset = Parcours.objects.filter(actif=True)
        query = self.request.GET.get("q", "").strip()
        current_type = self.request.GET.get("type", "").strip()

        if query:
            queryset = queryset.filter(Q(nom__icontains=query) | Q(description__icontains=query))
        if current_type:
            queryset = queryset.filter(type_parcours=current_type)
        return queryset

    def get_template_names(self):
        if self.request.headers.get("HX-Request"):
            return ["formations/partials/parcours_results.html"]
        return [self.template_name]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["query"] = self.request.GET.get("q", "")
        context["current_type"] = self.request.GET.get("type", "")
        context["type_choices"] = Parcours.TypeParcours.choices
        context["tarifs"] = Tarif.objects.filter(actif=True)
        context["disciplines"] = Discipline.objects.all()
        return context


class ParcoursDetailView(DetailView):
    model = Parcours
    template_name = "formations/parcours_detail.html"
    context_object_name = "parcours"
    queryset = Parcours.objects.filter(actif=True)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["cours"] = self.object.cours.filter(actif=True).select_related("discipline")
        context["tarifs"] = Tarif.objects.filter(actif=True)
        return context


class CoursDetailView(DetailView):
    model = Cours
    template_name = "formations/cours_detail.html"
    context_object_name = "cours"
    queryset = Cours.objects.filter(actif=True).select_related("discipline")


@method_decorator(cache_page(600), name="dispatch")  # 10 min
class ProfesseurListView(ListView):
    model = Professeur
    template_name = "formations/professeur_list.html"
    context_object_name = "professeurs"
    queryset = Professeur.objects.filter(actif=True).prefetch_related("disciplines")


class ProfesseurDetailView(DetailView):
    model = Professeur
    template_name = "formations/professeur_detail.html"
    context_object_name = "professeur"
    queryset = Professeur.objects.filter(actif=True).prefetch_related("disciplines")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["autres_professeurs"] = (
            Professeur.objects.filter(actif=True)
            .exclude(pk=self.object.pk)
            .prefetch_related("disciplines")[:4]
        )
        return context
