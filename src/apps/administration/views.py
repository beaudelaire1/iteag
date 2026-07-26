import csv

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DeleteView, DetailView, ListView, TemplateView, UpdateView

from apps.academics.models import (
    CoursDeSession,
    DemandeInscriptionCours,
    Paiement,
    ProfilEtudiant,
    SessionAcademique,
)
from apps.accounts.models import User
from apps.admissions.models import DossierCandidature
from apps.admissions.services import available_status_choices, transition_dossier
from apps.core.mixins import AdminRoleRequiredMixin, SecretariatRoleRequiredMixin, StaffRoleRequiredMixin
from apps.formations.models import Cours, Discipline, Parcours, Professeur, Tarif
from apps.library.models import NoticeBibliographique

from .forms import (
    AdminEtudiantForm,
    AdminProfesseurForm,
    AdminSessionForm,
    AdminUserCreateForm,
    AdminUserForm,
)


def _safe_csv_cell(value):
    """Neutralise les cellules interprétables comme formules par les tableurs."""
    text = str(value or "")
    return f"'{text}" if text.lstrip().startswith(("=", "+", "-", "@")) else text


# ──────────────────────────────────────────────
# Dashboard
# ──────────────────────────────────────────────


class AdminDashboardView(AdminRoleRequiredMixin, TemplateView):
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
                    Q(date_debut__lte=today, date_fin__gte=today) | Q(statut=SessionAcademique.StatutSession.EN_COURS)
                ).first(),
                "prochaine_session": SessionAcademique.objects.filter(date_debut__gt=today)
                .order_by("date_debut")
                .first(),
                "derniers_dossiers": DossierCandidature.objects.select_related("parcours_souhaite")[:5],
                "derniers_paiements": Paiement.objects.select_related("etudiant__utilisateur", "session")[:5],
                "demandes_inscription_a_traiter": DemandeInscriptionCours.objects.filter(
                    statut__in=[
                        DemandeInscriptionCours.Statut.SOUMISE,
                        DemandeInscriptionCours.Statut.PAIEMENT_ATTENTE,
                    ]
                ).count(),
                "cours_ouverts_inscription": CoursDeSession.objects.filter(
                    inscriptions_ouvertes=True,
                    statut=CoursDeSession.StatutCours.PROGRAMME,
                    session__date_fin__gte=today,
                ).count(),
            }
        )
        return ctx


class SecretariatDashboardView(SecretariatRoleRequiredMixin, TemplateView):
    template_name = "administration/secretariat_dashboard.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        today = timezone.localdate()
        ctx.update(
            {
                "candidatures_a_traiter": DossierCandidature.objects.filter(
                    statut__in=[
                        DossierCandidature.Statut.SOUMIS,
                        DossierCandidature.Statut.EN_EXAMEN,
                        DossierCandidature.Statut.INCOMPLET,
                    ]
                ).count(),
                "candidatures_nouvelles": DossierCandidature.objects.filter(
                    statut=DossierCandidature.Statut.SOUMIS
                ).count(),
                "etudiants_actifs": ProfilEtudiant.objects.filter(statut_inscription="actif").count(),
                "paiements_en_attente": Paiement.objects.filter(statut=Paiement.StatutPaiement.EN_ATTENTE).count(),
                "demandes_inscription_a_traiter": DemandeInscriptionCours.objects.filter(
                    statut__in=[
                        DemandeInscriptionCours.Statut.SOUMISE,
                        DemandeInscriptionCours.Statut.PAIEMENT_ATTENTE,
                    ]
                ).count(),
                "dossiers_recents": DossierCandidature.objects.select_related("parcours_souhaite")[:8],
                "demandes_inscription_recentes": DemandeInscriptionCours.objects.filter(
                    statut__in=[
                        DemandeInscriptionCours.Statut.SOUMISE,
                        DemandeInscriptionCours.Statut.PAIEMENT_ATTENTE,
                    ]
                )
                .select_related("etudiant__utilisateur", "cours_session__cours", "cours_session__session")
                .order_by("created_at")[:8],
                "session_en_cours": SessionAcademique.objects.filter(
                    Q(date_debut__lte=today, date_fin__gte=today) | Q(statut=SessionAcademique.StatutSession.EN_COURS)
                ).first(),
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
            s[0]: DossierCandidature.objects.filter(statut=s[0]).count() for s in DossierCandidature.Statut.choices
        }
        return ctx


class AdminCandidatureDetailView(StaffRoleRequiredMixin, DetailView):
    model = DossierCandidature
    template_name = "administration/candidature_detail.html"
    context_object_name = "dossier"

    def get_context_data(self, **kwargs):
        from apps.academics.models import Promotion

        ctx = super().get_context_data(**kwargs)
        ctx["statut_choices"] = available_status_choices(self.object)
        ctx["historique"] = self.object.historique.select_related("modifie_par")
        ctx["promotions"] = Promotion.objects.filter(actif=True, parcours=self.object.parcours_souhaite).order_by(
            "-annee_debut"
        )
        return ctx

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        new_statut = request.POST.get("statut")
        commentaire = request.POST.get("commentaire", "")

        if not new_statut or new_statut == self.object.statut:
            return redirect("administration:candidature_detail", pk=self.object.pk)

        # L'acceptation ne se limite pas à un changement de statut : elle crée le
        # compte, le profil et ouvre les accès aux modules. La transition
        # elle-même reste gouvernée par la machine à états d'admissions.
        if new_statut == DossierCandidature.Statut.ACCEPTE:
            return self._accepter(request, commentaire)

        try:
            self.object = transition_dossier(
                dossier=self.object,
                new_status=new_statut,
                changed_by=request.user,
                comment=commentaire,
            )
        except ValidationError as exc:
            messages.error(request, exc.messages[0])
        else:
            messages.success(request, f"Statut mis à jour : {self.object.get_statut_display()}")
        return redirect("administration:candidature_detail", pk=self.object.pk)

    def _accepter(self, request, commentaire):
        """L'acceptation crée le compte, le profil et ouvre les accès aux modules."""
        from apps.academics.models import Promotion
        from apps.administration.services.admission import accepter_dossier

        promotion = Promotion.objects.filter(pk=request.POST.get("promotion"), actif=True).first()
        if promotion is None:
            messages.error(
                request,
                "Choisissez la promotion d'affectation : elle est nécessaire pour créer le dossier étudiant.",
            )
            return redirect("administration:candidature_detail", pk=self.object.pk)

        try:
            profil = accepter_dossier(self.object, promotion=promotion, par=request.user, request=request)
        except ValidationError as exc:
            messages.error(request, exc.messages[0])
        else:
            messages.success(
                request,
                f"Candidature acceptée. Compte {profil.numero_etudiant} créé, "
                f"{profil.inscriptions_modules.count()} module(s) ouvert(s), email de bienvenue envoyé.",
            )
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


class AdminProfesseurListView(AdminRoleRequiredMixin, ListView):
    model = Professeur
    template_name = "administration/professeurs.html"
    context_object_name = "professeurs"
    paginate_by = 20
    queryset = Professeur.objects.prefetch_related("disciplines")


# ──────────────────────────────────────────────
# Formations
# ──────────────────────────────────────────────


class AdminFormationsView(AdminRoleRequiredMixin, TemplateView):
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


class AdminUserListView(AdminRoleRequiredMixin, ListView):
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


class AdminUserCreateView(AdminRoleRequiredMixin, CreateView):
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


class AdminUserUpdateView(AdminRoleRequiredMixin, UpdateView):
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


class AdminUserDeleteView(AdminRoleRequiredMixin, DeleteView):
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


class AdminSessionDeleteView(AdminRoleRequiredMixin, DeleteView):
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


class AdminProfesseurCreateView(AdminRoleRequiredMixin, CreateView):
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


class AdminProfesseurUpdateView(AdminRoleRequiredMixin, UpdateView):
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


class AdminProfesseurDeleteView(AdminRoleRequiredMixin, DeleteView):
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


class AdminEtudiantDeleteView(AdminRoleRequiredMixin, DeleteView):
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
        writer.writerow(
            [
                "Nom",
                "Prénom",
                "Email",
                "Téléphone",
                "Parcours souhaité",
                "Statut",
                "Église",
                "Église fondatrice",
                "Date soumission",
            ]
        )

        qs = DossierCandidature.objects.select_related("parcours_souhaite")
        statut = request.GET.get("statut")
        if statut:
            qs = qs.filter(statut=statut)

        for d in qs.iterator():
            writer.writerow(
                [
                    _safe_csv_cell(d.nom),
                    _safe_csv_cell(d.prenom),
                    _safe_csv_cell(d.email),
                    _safe_csv_cell(d.telephone),
                    _safe_csv_cell(str(d.parcours_souhaite) if d.parcours_souhaite else ""),
                    _safe_csv_cell(d.get_statut_display()),
                    _safe_csv_cell(d.eglise),
                    "Oui" if d.eglise_fondatrice else "Non",
                    d.date_soumission.strftime("%d/%m/%Y"),
                ]
            )
        return response


class ExportEtudiantsCsvView(StaffRoleRequiredMixin, View):
    """Export CSV des étudiants."""

    def get(self, request):
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="etudiants.csv"'
        response.write("\ufeff")

        writer = csv.writer(response, delimiter=";")
        writer.writerow(
            [
                "Numéro étudiant",
                "Nom",
                "Prénom",
                "Email",
                "Parcours",
                "Promotion",
                "Statut",
                "ECTS acquis",
                "Église fondatrice",
            ]
        )

        qs = ProfilEtudiant.objects.select_related(
            "utilisateur",
            "parcours",
            "promotion",
        )
        statut = request.GET.get("statut")
        if statut:
            qs = qs.filter(statut_inscription=statut)

        for e in qs.iterator():
            writer.writerow(
                [
                    _safe_csv_cell(e.numero_etudiant),
                    _safe_csv_cell(e.utilisateur.last_name),
                    _safe_csv_cell(e.utilisateur.first_name),
                    _safe_csv_cell(e.utilisateur.email),
                    _safe_csv_cell(str(e.parcours)),
                    _safe_csv_cell(e.promotion.nom if e.promotion else ""),
                    _safe_csv_cell(e.get_statut_inscription_display()),
                    e.total_ects_acquis,
                    "Oui" if e.eglise_fondatrice else "Non",
                ]
            )
        return response


class ExportPaiementsCsvView(StaffRoleRequiredMixin, View):
    """Export CSV des paiements."""

    def get(self, request):
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="paiements.csv"'
        response.write("\ufeff")

        writer = csv.writer(response, delimiter=";")
        writer.writerow(
            [
                "Étudiant",
                "Numéro étudiant",
                "Session",
                "Montant",
                "Date",
                "Mode",
                "Statut",
                "Référence",
            ]
        )

        qs = Paiement.objects.select_related("etudiant__utilisateur", "session")

        for p in qs.iterator():
            writer.writerow(
                [
                    _safe_csv_cell(p.etudiant.utilisateur.get_full_name()),
                    _safe_csv_cell(p.etudiant.numero_etudiant),
                    _safe_csv_cell(str(p.session) if p.session else ""),
                    str(p.montant),
                    p.date_paiement.strftime("%d/%m/%Y"),
                    _safe_csv_cell(p.get_mode_display()),
                    _safe_csv_cell(p.get_statut_display()),
                    _safe_csv_cell(p.reference),
                ]
            )
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

        dossiers = DossierCandidature.objects.filter(pk__in=ids).exclude(statut=new_statut)
        count = 0
        skipped = 0
        for dossier in dossiers:
            try:
                transition_dossier(
                    dossier=dossier,
                    new_status=new_statut,
                    changed_by=request.user,
                    comment="Action groupée",
                )
            except ValidationError:
                skipped += 1
            else:
                count += 1

        messages.success(request, f"{count} dossier(s) mis à jour → {DossierCandidature.Statut(new_statut).label}.")
        if skipped:
            messages.warning(request, f"{skipped} dossier(s) ignoré(s) : transition non autorisée.")
        return redirect("administration:candidatures")
