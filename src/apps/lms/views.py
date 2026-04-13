from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.views.generic import CreateView, DetailView, ListView, TemplateView, UpdateView

from apps.core.mixins import TeacherRoleRequiredMixin

from apps.academics.models import CoursDeSession

from .forms import AnnonceForm, GradeForm, RessourceUploadForm
from .models import Annonce, Evaluation


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def _get_professeur(request):
    return getattr(request.user, "profil_professeur", None)


def _teacher_courses(request):
    prof = _get_professeur(request)
    if prof is None:
        return CoursDeSession.objects.none()
    return CoursDeSession.objects.filter(enseignant=prof).select_related("cours", "session")


# ──────────────────────────────────────────────
# Dashboard
# ──────────────────────────────────────────────

class TeacherDashboardView(TeacherRoleRequiredMixin, TemplateView):
    template_name = "lms/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        professeur = _get_professeur(self.request)
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


# ──────────────────────────────────────────────
# Course detail
# ──────────────────────────────────────────────

class TeacherCourseDetailView(TeacherRoleRequiredMixin, DetailView):
    model = CoursDeSession
    template_name = "lms/course_detail.html"
    context_object_name = "cours_session"

    def get_queryset(self):
        professeur = _get_professeur(self.request)
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


# ──────────────────────────────────────────────
# Courses list
# ──────────────────────────────────────────────

class TeacherCoursesListView(TeacherRoleRequiredMixin, ListView):
    template_name = "lms/courses_list.html"
    context_object_name = "cours_list"

    def get_queryset(self):
        return _teacher_courses(self.request).prefetch_related("inscriptions")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["professeur"] = _get_professeur(self.request)
        return context


# ──────────────────────────────────────────────
# Evaluations list (all pending across courses)
# ──────────────────────────────────────────────

class TeacherEvaluationsListView(TeacherRoleRequiredMixin, ListView):
    template_name = "lms/evaluations_list.html"
    context_object_name = "evaluations"

    def get_queryset(self):
        prof = _get_professeur(self.request)
        if prof is None:
            return Evaluation.objects.none()
        return (
            Evaluation.objects.filter(cours_session__enseignant=prof)
            .select_related("etudiant__utilisateur", "cours_session__cours", "cours_session__session")
            .order_by("statut", "-created_at")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["professeur"] = _get_professeur(self.request)
        return context


# ──────────────────────────────────────────────
# Announcements list
# ──────────────────────────────────────────────

class TeacherAnnoncesListView(TeacherRoleRequiredMixin, ListView):
    template_name = "lms/annonces_list.html"
    context_object_name = "annonces"

    def get_queryset(self):
        prof = _get_professeur(self.request)
        if prof is None:
            return Annonce.objects.none()
        return Annonce.objects.filter(cours_session__enseignant=prof).select_related("cours_session__cours")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["professeur"] = _get_professeur(self.request)
        return context


# ──────────────────────────────────────────────
# Resource upload
# ──────────────────────────────────────────────

class TeacherResourceUploadView(TeacherRoleRequiredMixin, CreateView):
    model = None  # set via form
    form_class = RessourceUploadForm
    template_name = "lms/resource_form.html"

    def dispatch(self, request, *args, **kwargs):
        self.cours_session = get_object_or_404(_teacher_courses(request), pk=kwargs["cours_pk"])
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["cours_session"] = self.cours_session
        return context

    def form_valid(self, form):
        ressource = form.save(commit=False)
        ressource.cours_session = self.cours_session
        ressource.uploade_par = self.request.user
        ressource.save()
        messages.success(self.request, "Ressource ajoutée avec succès.")
        return redirect(reverse("lms:course_detail", kwargs={"pk": self.cours_session.pk}))


# ──────────────────────────────────────────────
# Grade evaluation
# ──────────────────────────────────────────────

class TeacherGradeEvaluationView(TeacherRoleRequiredMixin, UpdateView):
    model = Evaluation
    form_class = GradeForm
    template_name = "lms/grade_form.html"
    context_object_name = "evaluation"

    def get_queryset(self):
        prof = _get_professeur(self.request)
        if prof is None:
            return Evaluation.objects.none()
        return Evaluation.objects.filter(cours_session__enseignant=prof).select_related(
            "etudiant__utilisateur", "cours_session__cours", "cours_session__session"
        )

    def form_valid(self, form):
        evaluation = form.save(commit=False)
        evaluation.statut = Evaluation.StatutEvaluation.NOTE
        evaluation.date_notation = timezone.now()
        evaluation.save()
        messages.success(self.request, f"Note enregistrée pour {evaluation.etudiant.utilisateur.get_full_name()}.")
        return redirect(reverse("lms:course_detail", kwargs={"pk": evaluation.cours_session.pk}))


# ──────────────────────────────────────────────
# Publish grades (batch action)
# ──────────────────────────────────────────────

class TeacherPublishGradesView(TeacherRoleRequiredMixin, DetailView):
    """POST-only: publish all 'noté' evaluations for a course session."""

    model = CoursDeSession
    http_method_names = ["post"]

    def get_queryset(self):
        prof = _get_professeur(self.request)
        if prof is None:
            return CoursDeSession.objects.none()
        return CoursDeSession.objects.filter(enseignant=prof)

    def post(self, request, *args, **kwargs):
        cours_session = self.get_object()
        updated = cours_session.evaluations.filter(statut=Evaluation.StatutEvaluation.NOTE).update(
            statut=Evaluation.StatutEvaluation.PUBLIE
        )
        messages.success(request, f"{updated} évaluation(s) publiée(s).")
        return redirect(reverse("lms:course_detail", kwargs={"pk": cours_session.pk}))


# ──────────────────────────────────────────────
# Announcement create
# ──────────────────────────────────────────────

class TeacherAnnouncementCreateView(TeacherRoleRequiredMixin, CreateView):
    form_class = AnnonceForm
    template_name = "lms/announcement_form.html"

    def dispatch(self, request, *args, **kwargs):
        self.cours_session = get_object_or_404(_teacher_courses(request), pk=kwargs["cours_pk"])
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["cours_session"] = self.cours_session
        return context

    def form_valid(self, form):
        annonce = form.save(commit=False)
        annonce.cours_session = self.cours_session
        annonce.auteur = self.request.user
        annonce.save()
        messages.success(self.request, "Annonce publiée.")
        return redirect(reverse("lms:course_detail", kwargs={"pk": self.cours_session.pk}))


# ──────────────────────────────────────────────
# Announcement edit
# ──────────────────────────────────────────────

class TeacherAnnouncementUpdateView(TeacherRoleRequiredMixin, UpdateView):
    model = Annonce
    form_class = AnnonceForm
    template_name = "lms/announcement_form.html"
    context_object_name = "annonce"

    def get_queryset(self):
        prof = _get_professeur(self.request)
        if prof is None:
            return Annonce.objects.none()
        return Annonce.objects.filter(cours_session__enseignant=prof).select_related("cours_session__cours")

    def form_valid(self, form):
        form.save()
        messages.success(self.request, "Annonce modifiée.")
        return redirect(reverse("lms:annonces_list"))