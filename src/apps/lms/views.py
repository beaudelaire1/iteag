from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.views.generic import CreateView, DetailView, TemplateView, UpdateView

from apps.core.mixins import TeacherRoleRequiredMixin

from apps.academics.models import CoursDeSession

from .forms import AnnonceForm, GradeForm, RessourceUploadForm
from .models import Annonce, Evaluation


class TeacherDashboardView(TeacherRoleRequiredMixin, TemplateView):
    template_name = "lms/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        professeur = getattr(self.request.user, "profil_professeur", None)
        cours_assignes = CoursDeSession.objects.none()
        pending_evaluations = Evaluation.objects.none()
        recent_annonces = Annonce.objects.none()

        if professeur is not None:
            cours_assignes = CoursDeSession.objects.filter(enseignant=professeur).select_related("cours", "session")
            pending_evaluations = Evaluation.objects.filter(
                cours_session__enseignant=professeur,
                statut__in=[Evaluation.StatutEvaluation.SOUMIS, Evaluation.StatutEvaluation.EN_CORRECTION],
            ).select_related("etudiant__utilisateur", "cours_session__cours", "cours_session__session")[:8]
            recent_annonces = Annonce.objects.filter(cours_session__enseignant=professeur).select_related(
                "cours_session__cours"
            )[:5]

        context.update(
            {
                "professeur": professeur,
                "cours_assignes": cours_assignes,
                "pending_evaluations": pending_evaluations,
                "recent_annonces": recent_annonces,
            }
        )
        return context


class TeacherCourseDetailView(TeacherRoleRequiredMixin, DetailView):
    model = CoursDeSession
    template_name = "lms/course_detail.html"
    context_object_name = "cours_session"

    def get_queryset(self):
        professeur = getattr(self.request.user, "profil_professeur", None)
        queryset = CoursDeSession.objects.select_related("cours", "session", "enseignant")
        if professeur is None:
            return queryset.none()
        return queryset.filter(enseignant=professeur)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        cours_session = self.object
        context.update(
            {
                "inscriptions": cours_session.inscriptions.select_related("etudiant__utilisateur", "etudiant__parcours"),
                "ressources": cours_session.ressources.all(),
                "annonces": cours_session.annonces.all(),
                "evaluations": cours_session.evaluations.select_related("etudiant__utilisateur").all(),
            }
        )
        return context