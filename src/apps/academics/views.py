from django.contrib import messages
from django.db.models import Prefetch, Q
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views.generic import TemplateView, UpdateView

from apps.core.mixins import StudentRoleRequiredMixin
from apps.documents.models import DocumentAdministratif
from apps.lms.models import Annonce, Evaluation, RessourcePedagogique

from .forms import StudentSubmissionForm
from .models import CoursDeSession, CreditECTS, DemandeInscriptionCours, InscriptionSession, SessionAcademique


class StudentDashboardView(StudentRoleRequiredMixin, TemplateView):
    template_name = "academics/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        profil = self.request.user.profil_etudiant
        today = timezone.localdate()

        current_session = (
            SessionAcademique.objects.filter(
                Q(date_debut__lte=today, date_fin__gte=today) | Q(statut=SessionAcademique.StatutSession.EN_COURS)
            )
            .order_by("date_debut")
            .first()
        )
        prochaine_session = SessionAcademique.objects.filter(date_debut__gt=today).order_by("date_debut").first()

        context.update(
            {
                "profil": profil,
                "current_session": current_session,
                "prochaine_session": prochaine_session,
                "progress_percent": round((profil.total_ects_acquis / profil.parcours.ects_requis) * 100)
                if profil.parcours.ects_requis
                else 0,
                "pending_evaluations": profil.evaluations.select_related(
                    "cours_session__cours", "cours_session__session"
                ).exclude(statut=Evaluation.StatutEvaluation.PUBLIE)[:5],
                "recent_resources": RessourcePedagogique.objects.filter(
                    cours_session__inscriptions__etudiant=profil,
                    visible_etudiants=True,
                )
                .select_related("cours_session__cours", "cours_session__session")
                .distinct()[:6],
                "recent_annonces": Annonce.objects.filter(
                    cours_session__inscriptions__etudiant=profil,
                )
                .select_related("cours_session__cours")
                .distinct()[:5],
                "inscriptions": profil.inscriptions.select_related(
                    "cours_session__cours", "cours_session__session", "cours_session__enseignant"
                ).prefetch_related(
                    Prefetch(
                        "cours_session__ressources",
                        queryset=RessourcePedagogique.objects.filter(visible_etudiants=True).order_by("-created_at"),
                    )
                )[:6],
                "documents_count": DocumentAdministratif.objects.filter(etudiant=self.request.user).count(),
                "latest_payments": profil.paiements.select_related("session")[:4],
                "demandes_en_cours": profil.demandes_inscription.filter(
                    statut__in=[
                        DemandeInscriptionCours.Statut.SOUMISE,
                        DemandeInscriptionCours.Statut.PAIEMENT_ATTENTE,
                    ]
                ).count(),
                "demandes_paiement": profil.demandes_inscription.filter(
                    statut=DemandeInscriptionCours.Statut.PAIEMENT_ATTENTE
                ).count(),
                "cours_catalogue_count": CoursDeSession.objects.filter(
                    cours__actif=True,
                    inscriptions_ouvertes=True,
                    statut=CoursDeSession.StatutCours.PROGRAMME,
                    session__date_fin__gte=today,
                )
                .filter(Q(cours__parcours=profil.parcours) | Q(cours__parcours__isnull=True))
                .distinct()
                .count(),
            }
        )
        return context


class StudentProgressView(StudentRoleRequiredMixin, TemplateView):
    template_name = "academics/progress.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        profil = self.request.user.profil_etudiant
        context.update(
            {
                "profil": profil,
                "credits": profil.credits_ects.select_related("cours", "session").order_by("-date_validation"),
                "stages": profil.stages.select_related("tuteur"),
                "vaes": profil.vaes.all(),
                "paiements": profil.paiements.select_related("session"),
                "documents": self.request.user.documents_administratifs.all()[:6],
                "credits_iteag": CreditECTS.objects.filter(etudiant=profil, source=CreditECTS.SourceCredit.ITEAG),
                "credits_flte": CreditECTS.objects.filter(etudiant=profil, source=CreditECTS.SourceCredit.FLTE),
            }
        )
        return context


class StudentCoursesView(StudentRoleRequiredMixin, TemplateView):
    """ETU-003 — Accès aux cours et ressources."""

    template_name = "academics/courses.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        profil = self.request.user.profil_etudiant
        inscriptions = (
            InscriptionSession.objects.filter(etudiant=profil)
            .select_related("cours_session__cours", "cours_session__session", "cours_session__enseignant")
            .prefetch_related(
                Prefetch(
                    "cours_session__ressources",
                    queryset=RessourcePedagogique.objects.filter(visible_etudiants=True).order_by("-created_at"),
                ),
                "cours_session__annonces",
            )
            .order_by("-cours_session__session__date_debut")
        )
        context.update({"profil": profil, "inscriptions": inscriptions})
        return context


class StudentGradesView(StudentRoleRequiredMixin, TemplateView):
    """ETU-006 — Consultation des notes et appréciations."""

    template_name = "academics/grades.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        profil = self.request.user.profil_etudiant
        evaluations = (
            Evaluation.objects.filter(etudiant=profil)
            .select_related("cours_session__cours", "cours_session__session")
            .order_by("-cours_session__session__date_debut", "cours_session__cours__titre")
        )
        published = evaluations.filter(statut=Evaluation.StatutEvaluation.PUBLIE)
        pending = evaluations.exclude(statut=Evaluation.StatutEvaluation.PUBLIE)
        context.update({"profil": profil, "published_grades": published, "pending_grades": pending})
        return context


class StudentEvaluationSubmitView(StudentRoleRequiredMixin, UpdateView):
    form_class = StudentSubmissionForm
    template_name = "academics/submission_form.html"
    context_object_name = "evaluation"

    def get_object(self, queryset=None):
        return get_object_or_404(
            Evaluation.objects.select_related("cours_session__cours", "cours_session__session"),
            pk=self.kwargs["pk"],
            etudiant=self.request.user.profil_etudiant,
            statut=Evaluation.StatutEvaluation.EN_ATTENTE,
        )

    def form_valid(self, form):
        evaluation = form.save(commit=False)
        evaluation.statut = Evaluation.StatutEvaluation.SOUMIS
        evaluation.date_soumission = timezone.now()
        evaluation.save(update_fields=["fichier_soumis", "statut", "date_soumission", "updated_at"])
        messages.success(self.request, "Votre travail a été remis. L'enseignant peut maintenant le corriger.")
        return redirect("academics:grades")
