"""Pilotage opérationnel des cours, inscriptions et paiements."""

from pathlib import Path

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Count, Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from apps.academics.models import CoursDeSession, DemandeInscriptionCours, Paiement, SessionAcademique
from apps.academics.services.inscriptions import traiter_demande
from apps.core.mixins import AdminRoleRequiredMixin, StaffRoleRequiredMixin
from apps.formations.models import Cours, Discipline

from .forms import AdminCoursForm, CoursDeSessionForm, EnrollmentDecisionForm, PaiementForm


class EnrollmentRequestListView(StaffRoleRequiredMixin, ListView):
    model = DemandeInscriptionCours
    template_name = "administration/enrollment_requests.html"
    context_object_name = "demandes"
    paginate_by = 25

    def get_queryset(self):
        queryset = DemandeInscriptionCours.objects.select_related(
            "etudiant__utilisateur",
            "etudiant__parcours",
            "cours_session__cours",
            "cours_session__session",
            "paiement",
        )
        statut = self.request.GET.get("statut", "")
        session = self.request.GET.get("session", "")
        recherche = self.request.GET.get("q", "").strip()
        if statut:
            queryset = queryset.filter(statut=statut)
        if session:
            queryset = queryset.filter(cours_session__session_id=session)
        if recherche:
            queryset = queryset.filter(
                Q(etudiant__utilisateur__first_name__icontains=recherche)
                | Q(etudiant__utilisateur__last_name__icontains=recherche)
                | Q(etudiant__numero_etudiant__icontains=recherche)
                | Q(cours_session__cours__titre__icontains=recherche)
            )
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "statuts": DemandeInscriptionCours.Statut.choices,
                "sessions": SessionAcademique.objects.order_by("-date_debut"),
                "current_statut": self.request.GET.get("statut", ""),
                "current_session": self.request.GET.get("session", ""),
                "query": self.request.GET.get("q", ""),
                "counts": {
                    statut: DemandeInscriptionCours.objects.filter(statut=statut).count()
                    for statut, _ in DemandeInscriptionCours.Statut.choices
                },
            }
        )
        return context


class EnrollmentRequestDetailView(StaffRoleRequiredMixin, DetailView):
    model = DemandeInscriptionCours
    template_name = "administration/enrollment_request_detail.html"
    context_object_name = "demande"
    queryset = DemandeInscriptionCours.objects.select_related(
        "etudiant__utilisateur",
        "etudiant__parcours",
        "etudiant__promotion",
        "cours_session__cours",
        "cours_session__session",
        "cours_session__enseignant",
        "paiement",
        "traitee_par",
    )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "decision_form": EnrollmentDecisionForm(demande=self.object),
                "historique": self.object.historique.select_related("modifie_par"),
                "paiements_compatibles": Paiement.objects.filter(
                    etudiant=self.object.etudiant,
                    session=self.object.cours_session.session,
                ).order_by("-date_paiement"),
            }
        )
        return context


class EnrollmentRequestActionView(StaffRoleRequiredMixin, View):
    http_method_names = ["post"]

    def post(self, request, *args, **kwargs):
        demande = get_object_or_404(DemandeInscriptionCours, pk=kwargs["pk"])
        form = EnrollmentDecisionForm(request.POST, demande=demande)
        if not form.is_valid():
            for erreurs in form.errors.values():
                for erreur in erreurs:
                    messages.error(request, erreur)
            return redirect("administration:enrollment_request_detail", pk=demande.pk)
        try:
            traiter_demande(
                demande=demande,
                par=request.user,
                request=request,
                **form.cleaned_data,
            )
        except ValidationError as exc:
            messages.error(request, exc.messages[0])
        else:
            messages.success(request, "La demande d'inscription a été mise à jour.")
        return redirect("administration:enrollment_request_detail", pk=demande.pk)


class EnrollmentProofDownloadView(StaffRoleRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        demande = get_object_or_404(DemandeInscriptionCours, pk=kwargs["pk"])
        if not demande.justificatif_paiement:
            raise Http404("Justificatif indisponible.")
        return FileResponse(
            demande.justificatif_paiement.open("rb"),
            as_attachment=True,
            filename=Path(demande.justificatif_paiement.name).name,
        )


class CourseOfferingListView(StaffRoleRequiredMixin, ListView):
    model = CoursDeSession
    template_name = "administration/course_offerings.html"
    context_object_name = "offres"
    paginate_by = 25

    def get_queryset(self):
        queryset = (
            CoursDeSession.objects.select_related("cours__discipline", "session", "enseignant")
            .annotate(
                nombre_inscrits=Count("inscriptions", distinct=True),
                nombre_demandes=Count("demandes_inscription", distinct=True),
            )
            .order_by("-session__date_debut", "cours__titre")
        )
        session = self.request.GET.get("session", "")
        statut = self.request.GET.get("statut", "")
        recherche = self.request.GET.get("q", "").strip()
        if session:
            queryset = queryset.filter(session_id=session)
        if statut:
            queryset = queryset.filter(statut=statut)
        if recherche:
            queryset = queryset.filter(
                Q(cours__titre__icontains=recherche)
                | Q(cours__code__icontains=recherche)
                | Q(enseignant__nom__icontains=recherche)
            )
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "sessions": SessionAcademique.objects.order_by("-date_debut"),
                "statuts": CoursDeSession.StatutCours.choices,
                "current_session": self.request.GET.get("session", ""),
                "current_statut": self.request.GET.get("statut", ""),
                "query": self.request.GET.get("q", ""),
            }
        )
        return context


class CourseOfferingCreateView(StaffRoleRequiredMixin, CreateView):
    model = CoursDeSession
    form_class = CoursDeSessionForm
    template_name = "administration/form.html"
    success_url = reverse_lazy("administration:course_offerings")

    def get_initial(self):
        initial = super().get_initial()
        initial["cours"] = self.request.GET.get("cours")
        initial["session"] = self.request.GET.get("session")
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "form_title": "Programmer un cours",
                "nav": "course_offerings",
                "cancel_url": reverse("administration:course_offerings"),
            }
        )
        return context

    def form_valid(self, form):
        messages.success(self.request, "Le cours a été ajouté au catalogue de la session.")
        return super().form_valid(form)


class CourseOfferingUpdateView(StaffRoleRequiredMixin, UpdateView):
    model = CoursDeSession
    form_class = CoursDeSessionForm
    template_name = "administration/form.html"
    success_url = reverse_lazy("administration:course_offerings")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "form_title": f"Modifier — {self.object}",
                "nav": "course_offerings",
                "cancel_url": reverse("administration:course_offerings"),
            }
        )
        return context

    def form_valid(self, form):
        messages.success(self.request, "La programmation du cours a été mise à jour.")
        return super().form_valid(form)


class CourseOfferingDeleteView(AdminRoleRequiredMixin, DeleteView):
    model = CoursDeSession
    template_name = "administration/confirm_delete.html"
    success_url = reverse_lazy("administration:course_offerings")

    def form_valid(self, form):
        if self.object.inscriptions.exists() or self.object.demandes_inscription.exists():
            messages.error(
                self.request,
                "Ce cours possède des inscriptions ou des demandes : fermez-le au lieu de le supprimer.",
            )
            return redirect("administration:course_offerings")
        messages.success(self.request, "La programmation du cours a été supprimée.")
        return super().form_valid(form)


class PaymentListView(StaffRoleRequiredMixin, ListView):
    model = Paiement
    template_name = "administration/payments.html"
    context_object_name = "paiements"
    paginate_by = 30

    def get_queryset(self):
        queryset = Paiement.objects.select_related("etudiant__utilisateur", "session")
        statut = self.request.GET.get("statut", "")
        session = self.request.GET.get("session", "")
        recherche = self.request.GET.get("q", "").strip()
        if statut:
            queryset = queryset.filter(statut=statut)
        if session:
            queryset = queryset.filter(session_id=session)
        if recherche:
            queryset = queryset.filter(
                Q(etudiant__utilisateur__last_name__icontains=recherche)
                | Q(etudiant__utilisateur__first_name__icontains=recherche)
                | Q(etudiant__numero_etudiant__icontains=recherche)
                | Q(reference__icontains=recherche)
            )
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "sessions": SessionAcademique.objects.order_by("-date_debut"),
                "statuts": Paiement.StatutPaiement.choices,
                "current_statut": self.request.GET.get("statut", ""),
                "current_session": self.request.GET.get("session", ""),
                "query": self.request.GET.get("q", ""),
                "total_en_attente": Paiement.objects.filter(statut=Paiement.StatutPaiement.EN_ATTENTE).count(),
                "total_confirmes": Paiement.objects.filter(statut=Paiement.StatutPaiement.CONFIRME).count(),
            }
        )
        return context


class PaymentCreateView(StaffRoleRequiredMixin, CreateView):
    model = Paiement
    form_class = PaiementForm
    template_name = "administration/form.html"

    def get_initial(self):
        initial = super().get_initial()
        initial.update(
            {
                "etudiant": self.request.GET.get("etudiant"),
                "session": self.request.GET.get("session"),
                "montant": self.request.GET.get("montant"),
                "reference": self.request.GET.get("reference", ""),
            }
        )
        return initial

    def get_success_url(self):
        demande_id = self.request.GET.get("demande")
        if demande_id:
            return reverse("administration:enrollment_request_detail", kwargs={"pk": demande_id})
        return reverse("administration:payments")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "form_title": "Enregistrer un paiement",
                "nav": "payments",
                "cancel_url": self.get_success_url(),
            }
        )
        return context

    def form_valid(self, form):
        messages.success(self.request, "Le paiement a été enregistré.")
        return super().form_valid(form)


class PaymentUpdateView(StaffRoleRequiredMixin, UpdateView):
    model = Paiement
    form_class = PaiementForm
    template_name = "administration/form.html"
    success_url = reverse_lazy("administration:payments")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "form_title": f"Modifier le paiement — {self.object.etudiant}",
                "nav": "payments",
                "cancel_url": reverse("administration:payments"),
            }
        )
        return context

    def form_valid(self, form):
        messages.success(self.request, "Le paiement a été mis à jour.")
        return super().form_valid(form)


class PaymentDeleteView(AdminRoleRequiredMixin, DeleteView):
    model = Paiement
    template_name = "administration/confirm_delete.html"
    success_url = reverse_lazy("administration:payments")

    def form_valid(self, form):
        if self.object.demandes_inscription.exists():
            messages.error(self.request, "Ce paiement justifie une inscription et ne peut pas être supprimé.")
            return redirect("administration:payments")
        messages.success(self.request, "Le paiement a été supprimé.")
        return super().form_valid(form)


class CourseListView(AdminRoleRequiredMixin, ListView):
    model = Cours
    template_name = "administration/courses.html"
    context_object_name = "cours_list"
    paginate_by = 30

    def get_queryset(self):
        queryset = (
            Cours.objects.select_related("discipline")
            .prefetch_related("parcours")
            .annotate(nombre_sessions=Count("sessions", distinct=True))
        )
        recherche = self.request.GET.get("q", "").strip()
        discipline = self.request.GET.get("discipline", "")
        if recherche:
            queryset = queryset.filter(Q(titre__icontains=recherche) | Q(code__icontains=recherche))
        if discipline:
            queryset = queryset.filter(discipline_id=discipline)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "disciplines": Discipline.objects.order_by("ordre", "nom"),
                "query": self.request.GET.get("q", ""),
                "current_discipline": self.request.GET.get("discipline", ""),
            }
        )
        return context


class CourseCreateView(AdminRoleRequiredMixin, CreateView):
    model = Cours
    form_class = AdminCoursForm
    template_name = "administration/form.html"
    success_url = reverse_lazy("administration:courses")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "form_title": "Créer un cours",
                "nav": "formations",
                "cancel_url": reverse("administration:courses"),
            }
        )
        return context

    def form_valid(self, form):
        messages.success(self.request, "Le cours a été créé dans le référentiel.")
        return super().form_valid(form)


class CourseUpdateView(AdminRoleRequiredMixin, UpdateView):
    model = Cours
    form_class = AdminCoursForm
    template_name = "administration/form.html"
    success_url = reverse_lazy("administration:courses")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "form_title": f"Modifier — {self.object.titre}",
                "nav": "formations",
                "cancel_url": reverse("administration:courses"),
            }
        )
        return context

    def form_valid(self, form):
        messages.success(self.request, "Le cours a été mis à jour.")
        return super().form_valid(form)


class CourseDeleteView(AdminRoleRequiredMixin, DeleteView):
    model = Cours
    template_name = "administration/confirm_delete.html"
    success_url = reverse_lazy("administration:courses")

    def form_valid(self, form):
        if self.object.sessions.exists():
            messages.error(self.request, "Ce cours a déjà été programmé : désactivez-le au lieu de le supprimer.")
            return redirect("administration:courses")
        return super().form_valid(form)
