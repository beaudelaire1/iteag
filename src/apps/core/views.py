import csv

from django.contrib import messages
from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views import View
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
            from apps.admissions.emails import send_statut_change_email

            HistoriqueStatut.objects.create(
                dossier=self.object,
                ancien_statut=self.object.statut,
                nouveau_statut=new_statut,
                modifie_par=request.user,
                commentaire=commentaire,
            )
            self.object.statut = new_statut
            self.object.save(update_fields=["statut"])
            send_statut_change_email(self.object)
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
        qs = ProfilEtudiant.objects.select_related("utilisateur", "parcours", "promotion").order_by(
            "utilisateur__last_name", "utilisateur__first_name"
        )
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


# ══════════════════════════════════════════════
# Exports CSV — CDC ADM-010
# ══════════════════════════════════════════════


class ExportCandidaturesCsvView(StaffRoleRequiredMixin, View):
    """Export CSV des candidatures avec filtrage optionnel par statut."""

    def get(self, request):
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="candidatures.csv"'
        response.write("\ufeff")  # BOM UTF-8 pour Excel

        writer = csv.writer(response, delimiter=";")
        writer.writerow([
            "Nom", "Prénom", "Email", "Téléphone", "Parcours souhaité",
            "Statut", "Église", "Église fondatrice", "Date soumission",
        ])

        qs = DossierCandidature.objects.select_related("parcours_souhaite")
        statut = request.GET.get("statut")
        if statut:
            qs = qs.filter(statut=statut)

        for d in qs.iterator():
            writer.writerow([
                d.nom, d.prenom, d.email, d.telephone,
                str(d.parcours_souhaite) if d.parcours_souhaite else "",
                d.get_statut_display(), d.eglise,
                "Oui" if d.eglise_fondatrice else "Non",
                d.date_soumission.strftime("%d/%m/%Y"),
            ])
        return response


class ExportEtudiantsCsvView(StaffRoleRequiredMixin, View):
    """Export CSV des étudiants."""

    def get(self, request):
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="etudiants.csv"'
        response.write("\ufeff")

        writer = csv.writer(response, delimiter=";")
        writer.writerow([
            "Numéro étudiant", "Nom", "Prénom", "Email", "Parcours",
            "Promotion", "Statut", "ECTS acquis", "Église fondatrice",
        ])

        qs = ProfilEtudiant.objects.select_related(
            "utilisateur", "parcours", "promotion",
        )
        statut = request.GET.get("statut")
        if statut:
            qs = qs.filter(statut_inscription=statut)

        for e in qs.iterator():
            writer.writerow([
                e.numero_etudiant,
                e.utilisateur.last_name, e.utilisateur.first_name,
                e.utilisateur.email, str(e.parcours),
                e.promotion.nom if e.promotion else "",
                e.get_statut_inscription_display(),
                e.total_ects_acquis,
                "Oui" if e.eglise_fondatrice else "Non",
            ])
        return response


class ExportPaiementsCsvView(StaffRoleRequiredMixin, View):
    """Export CSV des paiements."""

    def get(self, request):
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="paiements.csv"'
        response.write("\ufeff")

        writer = csv.writer(response, delimiter=";")
        writer.writerow([
            "Étudiant", "Numéro étudiant", "Session", "Montant",
            "Date", "Mode", "Statut", "Référence",
        ])

        qs = Paiement.objects.select_related("etudiant__utilisateur", "session")

        for p in qs.iterator():
            writer.writerow([
                p.etudiant.utilisateur.get_full_name(),
                p.etudiant.numero_etudiant,
                str(p.session) if p.session else "",
                str(p.montant), p.date_paiement.strftime("%d/%m/%Y"),
                p.get_mode_display(), p.get_statut_display(),
                p.reference,
            ])
        return response


# ══════════════════════════════════════════════
# Actions groupées — Candidatures
# ══════════════════════════════════════════════


class BulkCandidatureStatusView(StaffRoleRequiredMixin, View):
    """Changement de statut en masse pour les candidatures sélectionnées."""

    def post(self, request):
        ids = request.POST.getlist("selected")
        new_statut = request.POST.get("bulk_statut")

        if not ids or not new_statut:
            messages.warning(request, "Sélectionnez des dossiers et un statut.")
            return redirect("administration:candidatures")

        valid_statuts = {s[0] for s in DossierCandidature.Statut.choices}
        if new_statut not in valid_statuts:
            messages.error(request, "Statut invalide.")
            return redirect("administration:candidatures")

        from apps.admissions.models import HistoriqueStatut

        dossiers = DossierCandidature.objects.filter(pk__in=ids).exclude(statut=new_statut)
        count = 0
        for dossier in dossiers:
            HistoriqueStatut.objects.create(
                dossier=dossier,
                ancien_statut=dossier.statut,
                nouveau_statut=new_statut,
                modifie_par=request.user,
                commentaire="Action groupée",
            )
            dossier.statut = new_statut
            dossier.save(update_fields=["statut"])
            count += 1

        messages.success(request, f"{count} dossier(s) mis à jour → {DossierCandidature.Statut(new_statut).label}.")
        return redirect("administration:candidatures")
