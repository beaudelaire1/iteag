from django.contrib import messages
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, DeleteView, DetailView, ListView, TemplateView, UpdateView

from .forms import (
    AdminEtudiantForm,
    AdminProfesseurForm,
    AdminSessionForm,
    AdminUserCreateForm,
    AdminUserForm,
)
from .mixins import StaffRoleRequiredMixin

from apps.accounts.models import User
from apps.academics.models import CoursDeSession, Paiement, ProfilEtudiant, Promotion, SessionAcademique
from apps.admissions.models import DossierCandidature
from apps.formations.models import Cours, Discipline, Parcours, Professeur, Tarif
from apps.library.models import NoticeBibliographique


# ──────────────────────────────────────────────
# Dashboard
# ──────────────────────────────────────────────


class AdminDashboardView(StaffRoleRequiredMixin, TemplateView):
    template_name = "administration/dashboard.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        today = timezone.localdate()

        candidatures_nouvelles = DossierCandidature.objects.filter(statut=DossierCandidature.Statut.SOUMIS).count()
        candidatures_examen = DossierCandidature.objects.filter(statut=DossierCandidature.Statut.EN_EXAMEN).count()

        ctx.update(
            {
                "total_etudiants": ProfilEtudiant.objects.count(),
                "etudiants_actifs": ProfilEtudiant.objects.filter(statut_inscription="actif").count(),
                "total_professeurs": Professeur.objects.filter(actif=True).count(),
                "total_candidatures": DossierCandidature.objects.count(),
                "candidatures_nouvelles": candidatures_nouvelles,
                "candidatures_examen": candidatures_examen,
                "total_cours": Cours.objects.filter(actif=True).count(),
                "total_parcours": Parcours.objects.filter(actif=True).count(),
                "total_ouvrages": NoticeBibliographique.objects.count(),
                "total_users": User.objects.filter(is_active=True).count(),
                "session_en_cours": SessionAcademique.objects.filter(
                    Q(date_debut__lte=today, date_fin__gte=today)
                    | Q(statut=SessionAcademique.StatutSession.EN_COURS)
                ).first(),
                "prochaine_session": SessionAcademique.objects.filter(date_debut__gt=today).order_by("date_debut").first(),
                "derniers_dossiers": DossierCandidature.objects.select_related("parcours_souhaite")[:5],
                "derniers_paiements": Paiement.objects.select_related("etudiant__utilisateur", "session")[:5],
            }
        )
        return ctx


# ──────────────────────────────────────────────
# Candidatures
# ──────────────────────────────────────────────


class AdminCandidatureListView(StaffRoleRequiredMixin, ListView):
    model = DossierCandidature
    template_name = "administration/candidatures.html"
    context_object_name = "dossiers"
    paginate_by = 20

    def get_queryset(self):
        qs = DossierCandidature.objects.select_related("parcours_souhaite")
        statut = self.request.GET.get("statut")
        q = self.request.GET.get("q", "").strip()
        if statut:
            qs = qs.filter(statut=statut)
        if q:
            qs = qs.filter(Q(nom__icontains=q) | Q(prenom__icontains=q) | Q(email__icontains=q))
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["statut_choices"] = DossierCandidature.Statut.choices
        ctx["current_statut"] = self.request.GET.get("statut", "")
        ctx["query"] = self.request.GET.get("q", "")
        ctx["counts"] = {
            s[0]: DossierCandidature.objects.filter(statut=s[0]).count()
            for s in DossierCandidature.Statut.choices
        }
        return ctx


class AdminCandidatureDetailView(StaffRoleRequiredMixin, DetailView):
    model = DossierCandidature
    template_name = "administration/candidature_detail.html"
    context_object_name = "dossier"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["statut_choices"] = DossierCandidature.Statut.choices
        ctx["historique"] = self.object.historique.select_related("modifie_par")
        return ctx

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        new_statut = request.POST.get("statut")
        commentaire = request.POST.get("commentaire", "")

        if new_statut and new_statut != self.object.statut:
            from apps.admissions.models import HistoriqueStatut

            HistoriqueStatut.objects.create(
                dossier=self.object,
                ancien_statut=self.object.statut,
                nouveau_statut=new_statut,
                modifie_par=request.user,
                commentaire=commentaire,
            )
            self.object.statut = new_statut
            self.object.save(update_fields=["statut"])
            messages.success(request, f"Statut mis à jour : {self.object.get_statut_display()}")
        return redirect("administration:candidature_detail", pk=self.object.pk)


# ──────────────────────────────────────────────
# Étudiants
# ──────────────────────────────────────────────


class AdminEtudiantListView(StaffRoleRequiredMixin, ListView):
    model = ProfilEtudiant
    template_name = "administration/etudiants.html"
    context_object_name = "etudiants"
    paginate_by = 20

    def get_queryset(self):
        qs = ProfilEtudiant.objects.select_related("utilisateur", "parcours", "promotion")
        q = self.request.GET.get("q", "").strip()
        statut = self.request.GET.get("statut")
        if q:
            qs = qs.filter(
                Q(utilisateur__last_name__icontains=q)
                | Q(utilisateur__first_name__icontains=q)
                | Q(numero_etudiant__icontains=q)
            )
        if statut:
            qs = qs.filter(statut_inscription=statut)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["statut_choices"] = ProfilEtudiant.StatutInscription.choices
        ctx["current_statut"] = self.request.GET.get("statut", "")
        ctx["query"] = self.request.GET.get("q", "")
        return ctx


# ──────────────────────────────────────────────
# Professeurs
# ──────────────────────────────────────────────


class AdminProfesseurListView(StaffRoleRequiredMixin, ListView):
    model = Professeur
    template_name = "administration/professeurs.html"
    context_object_name = "professeurs"
    paginate_by = 20
    queryset = Professeur.objects.prefetch_related("disciplines")


# ──────────────────────────────────────────────
# Formations
# ──────────────────────────────────────────────


class AdminFormationsView(StaffRoleRequiredMixin, TemplateView):
    template_name = "administration/formations.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["parcours_list"] = Parcours.objects.annotate(nb_cours=Count("cours"))
        ctx["disciplines"] = Discipline.objects.annotate(nb_cours=Count("cours"))
        ctx["tarifs"] = Tarif.objects.filter(actif=True)
        return ctx


# ──────────────────────────────────────────────
# Sessions
# ──────────────────────────────────────────────


class AdminSessionListView(StaffRoleRequiredMixin, ListView):
    model = SessionAcademique
    template_name = "administration/sessions.html"
    context_object_name = "sessions"
    paginate_by = 20


# ──────────────────────────────────────────────
# Utilisateurs
# ──────────────────────────────────────────────


class AdminUserListView(StaffRoleRequiredMixin, ListView):
    model = User
    template_name = "administration/utilisateurs.html"
    context_object_name = "users"
    paginate_by = 30

    def get_queryset(self):
        qs = User.objects.all()
        q = self.request.GET.get("q", "").strip()
        role = self.request.GET.get("role")
        if q:
            qs = qs.filter(Q(username__icontains=q) | Q(last_name__icontains=q) | Q(email__icontains=q))
        if role:
            qs = qs.filter(role=role)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["role_choices"] = User.Role.choices
        ctx["current_role"] = self.request.GET.get("role", "")
        ctx["query"] = self.request.GET.get("q", "")
        return ctx


# ══════════════════════════════════════════════
# CRUD — Utilisateurs
# ══════════════════════════════════════════════


class AdminUserCreateView(StaffRoleRequiredMixin, CreateView):
    model = User
    form_class = AdminUserCreateForm
    template_name = "administration/form.html"
    success_url = reverse_lazy("administration:utilisateurs")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["form_title"] = "Nouvel utilisateur"
        ctx["nav"] = "utilisateurs"
        return ctx

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f"Utilisateur « {self.object} » créé.")
        return response


class AdminUserUpdateView(StaffRoleRequiredMixin, UpdateView):
    model = User
    form_class = AdminUserForm
    template_name = "administration/form.html"
    success_url = reverse_lazy("administration:utilisateurs")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["form_title"] = f"Modifier — {self.object}"
        ctx["nav"] = "utilisateurs"
        return ctx

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f"Utilisateur « {self.object} » modifié.")
        return response


class AdminUserDeleteView(StaffRoleRequiredMixin, DeleteView):
    model = User
    template_name = "administration/confirm_delete.html"
    success_url = reverse_lazy("administration:utilisateurs")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["object_label"] = f"l'utilisateur « {self.object} »"
        ctx["nav"] = "utilisateurs"
        return ctx

    def form_valid(self, form):
        messages.success(self.request, f"Utilisateur « {self.object} » supprimé.")
        return super().form_valid(form)


# ══════════════════════════════════════════════
# CRUD — Sessions
# ══════════════════════════════════════════════


class AdminSessionCreateView(StaffRoleRequiredMixin, CreateView):
    model = SessionAcademique
    form_class = AdminSessionForm
    template_name = "administration/form.html"
    success_url = reverse_lazy("administration:sessions")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["form_title"] = "Nouvelle session académique"
        ctx["nav"] = "sessions"
        return ctx

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f"Session « {self.object} » créée.")
        return response


class AdminSessionUpdateView(StaffRoleRequiredMixin, UpdateView):
    model = SessionAcademique
    form_class = AdminSessionForm
    template_name = "administration/form.html"
    success_url = reverse_lazy("administration:sessions")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["form_title"] = f"Modifier — {self.object}"
        ctx["nav"] = "sessions"
        return ctx

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f"Session « {self.object} » modifiée.")
        return response


class AdminSessionDeleteView(StaffRoleRequiredMixin, DeleteView):
    model = SessionAcademique
    template_name = "administration/confirm_delete.html"
    success_url = reverse_lazy("administration:sessions")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["object_label"] = f"la session « {self.object} »"
        ctx["nav"] = "sessions"
        return ctx

    def form_valid(self, form):
        messages.success(self.request, f"Session « {self.object} » supprimée.")
        return super().form_valid(form)


# ══════════════════════════════════════════════
# CRUD — Professeurs
# ══════════════════════════════════════════════


class AdminProfesseurCreateView(StaffRoleRequiredMixin, CreateView):
    model = Professeur
    form_class = AdminProfesseurForm
    template_name = "administration/form.html"
    success_url = reverse_lazy("administration:professeurs")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["form_title"] = "Nouveau professeur"
        ctx["nav"] = "professeurs"
        return ctx

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f"Professeur « {self.object} » créé.")
        return response


class AdminProfesseurUpdateView(StaffRoleRequiredMixin, UpdateView):
    model = Professeur
    form_class = AdminProfesseurForm
    template_name = "administration/form.html"
    success_url = reverse_lazy("administration:professeurs")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["form_title"] = f"Modifier — {self.object}"
        ctx["nav"] = "professeurs"
        return ctx

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f"Professeur « {self.object} » modifié.")
        return response


class AdminProfesseurDeleteView(StaffRoleRequiredMixin, DeleteView):
    model = Professeur
    template_name = "administration/confirm_delete.html"
    success_url = reverse_lazy("administration:professeurs")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["object_label"] = f"le professeur « {self.object} »"
        ctx["nav"] = "professeurs"
        return ctx

    def form_valid(self, form):
        messages.success(self.request, f"Professeur « {self.object} » supprimé.")
        return super().form_valid(form)


# ══════════════════════════════════════════════
# CRUD — Étudiants
# ══════════════════════════════════════════════


class AdminEtudiantCreateView(StaffRoleRequiredMixin, CreateView):
    model = ProfilEtudiant
    form_class = AdminEtudiantForm
    template_name = "administration/form.html"
    success_url = reverse_lazy("administration:etudiants")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["form_title"] = "Nouveau profil étudiant"
        ctx["nav"] = "etudiants"
        return ctx

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f"Profil étudiant « {self.object} » créé.")
        return response


class AdminEtudiantUpdateView(StaffRoleRequiredMixin, UpdateView):
    model = ProfilEtudiant
    form_class = AdminEtudiantForm
    template_name = "administration/form.html"
    success_url = reverse_lazy("administration:etudiants")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["form_title"] = f"Modifier — {self.object}"
        ctx["nav"] = "etudiants"
        return ctx

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f"Profil étudiant « {self.object} » modifié.")
        return response


class AdminEtudiantDeleteView(StaffRoleRequiredMixin, DeleteView):
    model = ProfilEtudiant
    template_name = "administration/confirm_delete.html"
    success_url = reverse_lazy("administration:etudiants")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["object_label"] = f"le profil étudiant « {self.object} »"
        ctx["nav"] = "etudiants"
        return ctx

    def form_valid(self, form):
        messages.success(self.request, f"Profil étudiant « {self.object} » supprimé.")
        return super().form_valid(form)
