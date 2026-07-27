import csv
from decimal import Decimal

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Count, Q, Sum
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DeleteView, DetailView, ListView, TemplateView, UpdateView

from apps.academics.models import (
    CoursDeSession,
    DemandeInscriptionCours,
    InscriptionSession,
    Paiement,
    ProfilEtudiant,
    SessionAcademique,
)
from apps.accounts.models import User
from apps.administration.services import pilotage
from apps.administration.suppression import SuppressionProtegee
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
                # Production pédagogique des enseignants. Sans cette remontée,
                # un module créé côté enseignant n'existe pour l'administration
                # qu'une fois publié — trop tard pour relire quoi que ce soit.
                **self._production_pedagogique(),
            }
        )
        # Finances, échéances, activité, résultats et alertes. Le calcul vit
        # dans un service : ce sont des règles de gestion, pas de l'affichage.
        ctx.update(pilotage.finances(session_en_cours=ctx["session_en_cours"]))
        ctx.update(pilotage.formations())
        ctx.update(pilotage.resultats())
        ctx["echeances"] = pilotage.echeances()
        ctx["alertes"] = pilotage.alertes()
        return ctx

    def _production_pedagogique(self) -> dict:
        from apps.elearning.models import InscriptionModule, ModuleFormation

        modules = ModuleFormation.objects.select_related("responsable", "discipline")
        return {
            "demandes_acces_video": InscriptionModule.objects.filter(
                statut=InscriptionModule.StatutAcces.DEMANDE
            ).count(),
            "modules_en_relecture": modules.filter(statut=ModuleFormation.StatutPublication.RELECTURE).count(),
            "modules_brouillon": modules.filter(statut=ModuleFormation.StatutPublication.BROUILLON).count(),
            "modules_publies": modules.filter(statut=ModuleFormation.StatutPublication.PUBLIE).count(),
            "modules_recents": modules.exclude(statut=ModuleFormation.StatutPublication.ARCHIVE).order_by(
                "-updated_at"
            )[:5],
        }


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
                **self._demandes_acces_video(),
            }
        )
        return ctx

    def _demandes_acces_video(self) -> dict:
        """Les demandes d'accès aux modules attendent le secrétariat, comme les autres."""
        from apps.elearning.models import InscriptionModule

        demandes = InscriptionModule.objects.filter(statut=InscriptionModule.StatutAcces.DEMANDE)
        return {
            "demandes_acces_video": demandes.count(),
            "demandes_acces_video_recentes": demandes.select_related("module", "etudiant__utilisateur").order_by(
                "created_at"
            )[:8],
        }


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
        # Le total d'ECTS est annoté plutôt que calculé ligne par ligne : la
        # liste l'affiche pour chaque étudiant, et sans annotation le nombre de
        # requêtes croissait avec le nombre de lignes.
        qs = (
            ProfilEtudiant.objects.select_related("utilisateur", "parcours", "promotion")
            .annotate(ects_acquis_annotes=Coalesce(Sum("credits_ects__ects_obtenus"), Decimal("0")))
            .order_by("utilisateur__last_name", "utilisateur__first_name")
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


class AdminEtudiantDetailView(StaffRoleRequiredMixin, DetailView):
    """Fiche de scolarité complète — ce que le secrétariat cherchait dans cinq écrans.

    Coordonnées, église, parcours suivi, notes, crédits, paiements, accès
    e-learning et documents sont réunis ici. Chaque bloc est chargé en une
    requête : la fiche coûte un nombre fixe de requêtes, quel que soit le
    nombre de lignes affichées.
    """

    model = ProfilEtudiant
    template_name = "administration/etudiant_detail.html"
    context_object_name = "profil"

    def get_queryset(self):
        return ProfilEtudiant.objects.select_related("utilisateur", "parcours", "promotion", "formule_tarif")

    def get_context_data(self, **kwargs):
        from apps.documents.models import DocumentAdministratif
        from apps.elearning.models import InscriptionModule
        from apps.lms.models import Evaluation

        contexte = super().get_context_data(**kwargs)
        profil = self.object

        inscriptions = (
            InscriptionSession.objects.filter(etudiant=profil)
            .select_related("cours_session__cours", "cours_session__session", "cours_session__enseignant")
            .order_by("-cours_session__session__date_debut")
        )
        evaluations = (
            Evaluation.objects.filter(etudiant=profil)
            .select_related("cours_session__cours", "cours_session__session")
            .order_by("-created_at")
        )
        contexte.update(
            {
                "compte": profil.utilisateur,
                "inscriptions": inscriptions,
                "demandes": (
                    DemandeInscriptionCours.objects.filter(etudiant=profil)
                    .select_related("cours_session__cours", "cours_session__session")
                    .order_by("-created_at")[:10]
                ),
                "evaluations": evaluations,
                "notes_publiees": [e for e in evaluations if e.statut == Evaluation.StatutEvaluation.PUBLIE],
                "credits": profil.credits_ects.select_related("cours", "session", "stage", "vae").order_by(
                    "-date_validation"
                ),
                "paiements": profil.paiements.select_related("session").order_by("-date_paiement"),
                "acces_modules": (
                    InscriptionModule.objects.filter(etudiant=profil).select_related("module").order_by("-created_at")
                ),
                "documents": DocumentAdministratif.objects.filter(etudiant=profil.utilisateur).order_by("-created_at"),
                "total_regle": profil.paiements.filter(statut=Paiement.StatutPaiement.CONFIRME).aggregate(
                    total=Sum("montant")
                )["total"]
                or Decimal("0"),
            }
        )
        return contexte


# ──────────────────────────────────────────────
# Professeurs
# ──────────────────────────────────────────────


class AdminProfesseurListView(AdminRoleRequiredMixin, ListView):
    model = Professeur
    template_name = "administration/professeurs.html"
    context_object_name = "professeurs"
    paginate_by = 20

    def get_queryset(self):
        qs = Professeur.objects.prefetch_related("disciplines")
        q = self.request.GET.get("q", "").strip()
        actif = self.request.GET.get("actif", "")
        if q:
            qs = qs.filter(Q(nom__icontains=q) | Q(prenom__icontains=q) | Q(specialite__icontains=q))
        if actif in ("1", "0"):
            qs = qs.filter(actif=actif == "1")
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["query"] = self.request.GET.get("q", "")
        ctx["current_actif"] = self.request.GET.get("actif", "")
        return ctx


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

    def get_queryset(self):
        # Le nombre de sessions croît d'une année sur l'autre : sans filtre, la
        # session de l'an dernier se retrouve à la même distance que celle qui
        # commence la semaine prochaine.
        # L'ordre est réaffirmé après l'annotation : sans lui, la pagination
        # rendrait des pages qui se recouvrent.
        qs = SessionAcademique.objects.annotate(nombre_cours=Count("cours_de_session")).order_by("-date_debut")
        q = self.request.GET.get("q", "").strip()
        statut = self.request.GET.get("statut", "")
        annee = self.request.GET.get("annee", "")
        if q:
            qs = qs.filter(Q(nom__icontains=q) | Q(annee_academique__icontains=q))
        if statut:
            qs = qs.filter(statut=statut)
        if annee:
            qs = qs.filter(annee_academique=annee)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(
            {
                "query": self.request.GET.get("q", ""),
                "statut_choices": SessionAcademique.StatutSession.choices,
                "current_statut": self.request.GET.get("statut", ""),
                "annees": SessionAcademique.objects.values_list("annee_academique", flat=True)
                .distinct()
                .order_by("-annee_academique"),
                "current_annee": self.request.GET.get("annee", ""),
            }
        )
        return ctx


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


class AdminUserDeleteView(SuppressionProtegee, AdminRoleRequiredMixin, DeleteView):
    """
    Supprimer un compte emportait le profil étudiant en cascade, et avec lui
    inscriptions, notes, crédits ECTS et historique de paiements. En deux clics,
    sans avertissement.
    """

    model = User
    template_name = "administration/confirm_delete.html"
    success_url = reverse_lazy("administration:utilisateurs")
    url_retour = "administration:utilisateurs"

    def libelle(self):
        return f"l'utilisateur « {self.object} »"

    def raison_de_bloquer(self):
        if self.object.pk == self.request.user.pk:
            return "Vous ne pouvez pas supprimer votre propre compte."
        if hasattr(self.object, "profil_etudiant"):
            return (
                "Ce compte porte un dossier étudiant : sa suppression effacerait notes, crédits et "
                "paiements. Désactivez le compte, ou supprimez d'abord le dossier."
            )
        if hasattr(self.object, "profil_professeur"):
            return "Ce compte est rattaché à une fiche professeur : détachez-la d'abord, ou désactivez le compte."
        if self.object.is_active and self.object.role == User.Role.ADMIN:
            restants = User.objects.filter(is_active=True, role=User.Role.ADMIN).exclude(pk=self.object.pk).count()
            if restants == 0:
                return "C'est le dernier compte d'administration actif : le supprimer fermerait le portail à tous."
        return ""

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["nav"] = "utilisateurs"
        return ctx


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


class AdminSessionDeleteView(SuppressionProtegee, AdminRoleRequiredMixin, DeleteView):
    """Supprimer une session emportait en cascade tous ses cours programmés."""

    model = SessionAcademique
    template_name = "administration/confirm_delete.html"
    success_url = reverse_lazy("administration:sessions")
    url_retour = "administration:sessions"

    def libelle(self):
        return f"la session « {self.object} »"

    def raison_de_bloquer(self):
        if self.object.cours_de_session.exists():
            return (
                "Cette session porte des cours programmés : leur suppression entraînerait "
                "inscriptions, notes et annonces. Retirez d'abord la programmation, ou clôturez la session."
            )
        return ""

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["nav"] = "sessions"
        return ctx


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


class AdminProfesseurDeleteView(SuppressionProtegee, AdminRoleRequiredMixin, DeleteView):
    """
    « CoursDeSession.enseignant » est en PROTECT : sans ce garde-fou, la
    suppression produisait une erreur de base opaque au lieu d'une explication.
    """

    model = Professeur
    template_name = "administration/confirm_delete.html"
    success_url = reverse_lazy("administration:professeurs")
    url_retour = "administration:professeurs"

    def libelle(self):
        return f"le professeur « {self.object} »"

    def raison_de_bloquer(self):
        if self.object.cours_de_session.exists():
            return "Ce professeur est rattaché à des cours programmés : décochez « actif » plutôt que de supprimer."
        if self.object.modules_video.exists():
            return "Ce professeur est responsable de modules vidéo : réattribuez-les d'abord."
        return ""

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["nav"] = "professeurs"
        return ctx


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


class AdminEtudiantDeleteView(SuppressionProtegee, AdminRoleRequiredMixin, DeleteView):
    """
    Un dossier étudiant porte des notes, des crédits et des paiements. Un
    étudiant qui s'en va se désactive : il ne s'efface pas, sans quoi
    l'institut perdrait la trace de ce qu'il a délivré.
    """

    model = ProfilEtudiant
    template_name = "administration/confirm_delete.html"
    success_url = reverse_lazy("administration:etudiants")
    url_retour = "administration:etudiants"

    def libelle(self):
        return f"le profil étudiant « {self.object} »"

    def raison_de_bloquer(self):
        if self.object.credits_ects.exists():
            return "Ce dossier porte des crédits ECTS acquis : passez le statut à « inactif » au lieu de supprimer."
        if self.object.paiements.exists():
            return "Ce dossier porte un historique de paiements : passez le statut à « inactif » au lieu de supprimer."
        if self.object.evaluations.exists():
            return "Ce dossier porte des évaluations : passez le statut à « inactif » au lieu de supprimer."
        return ""

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["nav"] = "etudiants"
        return ctx


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
