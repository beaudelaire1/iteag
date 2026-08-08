"""Pilotage opérationnel des cours, inscriptions et paiements."""

from pathlib import Path

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Count, Q
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.text import slugify
from django.views import View
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from apps.academics.models import (
    VAE,
    CoursDeSession,
    CreditECTS,
    DemandeInscriptionCours,
    InscriptionSession,
    Paiement,
    PresenceEtudiant,
    ProfilEtudiant,
    Promotion,
    SessionAcademique,
    Stage,
)
from apps.academics.services.inscriptions import traiter_demande
from apps.accounts.models import User
from apps.core.mixins import StaffRoleRequiredMixin
from apps.core.models import Notification
from apps.core.services.audit import journaliser
from apps.core.services.notifications import notifier, notifier_plusieurs
from apps.formations.models import Cours, Discipline, Parcours, Tarif

from .forms import (
    AdminCoursForm,
    AdminDisciplineForm,
    AdminParcoursForm,
    CoursDeSessionForm,
    CreditECTSForm,
    EnrollmentDecisionForm,
    PaiementForm,
    PromotionForm,
    StageForm,
    TarifForm,
    VAEForm,
)
from .suppression import SuppressionProtegee


def _notifier_dossier_etudiant(objet, titre, message, url_cible):
    return notifier(
        objet.etudiant.utilisateur,
        titre,
        type_notification=Notification.Type.SYSTEME,
        message=message,
        url_cible=url_cible,
    )


def _notifier_cours_disponible(cours_session):
    if not cours_session.inscriptions_ouvertes:
        return 0
    destinataires = User.objects.filter(
        is_active=True,
        profil_etudiant__parcours__in=cours_session.cours.parcours.all(),
        profil_etudiant__statut_inscription__in=[
            ProfilEtudiant.StatutInscription.PRE_INSCRIT,
            ProfilEtudiant.StatutInscription.PAIEMENT_ATTENTE,
            ProfilEtudiant.StatutInscription.INSCRIT,
            ProfilEtudiant.StatutInscription.ACTIF,
        ],
    ).distinct()
    return notifier_plusieurs(
        destinataires,
        f"Cours disponible — {cours_session.cours.titre}",
        type_notification=Notification.Type.NOUVEAU_MODULE,
        message=(
            f"Le cours « {cours_session.cours.titre} » est ouvert aux inscriptions pour la session "
            f"« {cours_session.session.nom} ». Il correspond à votre parcours ; vous pouvez demander "
            "à le suivre depuis votre espace étudiant."
        ),
        details=_details_programmation(cours_session),
        url_cible=reverse("etudiant:course_offering_detail", kwargs={"pk": cours_session.pk}),
    )


def _details_programmation(cours_session) -> list[dict]:
    """Cours, session et enseignant : de quoi savoir de quelle séance on parle."""
    details = [
        {"libelle": "Cours", "valeur": cours_session.cours.titre},
        {"libelle": "Session", "valeur": cours_session.session.nom},
    ]
    if cours_session.enseignant_id:
        details.append({"libelle": "Enseignant", "valeur": str(cours_session.enseignant)})
    return details


def _notifier_programmation_cours(cours_session, *, creation=False):
    enseignant = getattr(cours_session.enseignant, "user", None)
    notifier(
        enseignant,
        f"Cours {'attribué' if creation else 'mis à jour'} — {cours_session.cours.titre}",
        type_notification=Notification.Type.RAPPEL_SESSION,
        message=(
            f"Le cours « {cours_session.cours.titre} » vous est "
            + ("attribué" if creation else "confié, et sa programmation vient d'être modifiée")
            + ". Vous en trouverez la fiche, les inscrits et les évaluations dans votre espace enseignant."
        ),
        details=_details_programmation(cours_session),
        url_cible=reverse("lms:course_detail", kwargs={"pk": cours_session.pk}),
    )
    inscrits = User.objects.filter(
        is_active=True,
        profil_etudiant__inscriptions__cours_session=cours_session,
    ).distinct()
    notifier_plusieurs(
        inscrits,
        f"Programmation mise à jour — {cours_session.cours.titre}",
        type_notification=Notification.Type.RAPPEL_SESSION,
        message=(
            f"La programmation du cours « {cours_session.cours.titre} » a été modifiée : dates, "
            "salle ou enseignant. Vérifiez les informations à jour dans votre espace avant la "
            "prochaine séance."
        ),
        details=_details_programmation(cours_session),
        url_cible=reverse("etudiant:courses"),
    )


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
        reponse = super().form_valid(form)
        _notifier_cours_disponible(self.object)
        _notifier_programmation_cours(self.object, creation=True)
        messages.success(self.request, "Le cours a été ajouté au catalogue de la session.")
        return reponse


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
        inscriptions_ouvertes_avant = self.object.inscriptions_ouvertes
        reponse = super().form_valid(form)
        if self.object.inscriptions_ouvertes and not inscriptions_ouvertes_avant:
            _notifier_cours_disponible(self.object)
        _notifier_programmation_cours(self.object)
        messages.success(self.request, "La programmation du cours a été mise à jour.")
        return reponse


class CourseOfferingDeleteView(StaffRoleRequiredMixin, DeleteView):
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
        reponse = super().form_valid(form)
        _notifier_dossier_etudiant(
            self.object,
            "Paiement enregistré",
            f"{self.object.montant} € — {self.object.get_statut_display()}.",
            reverse("etudiant:payments"),
        )
        messages.success(self.request, "Le paiement a été enregistré.")
        return reponse


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
        reponse = super().form_valid(form)
        _notifier_dossier_etudiant(
            self.object,
            "Paiement mis à jour",
            f"{self.object.montant} € — {self.object.get_statut_display()}.",
            reverse("etudiant:payments"),
        )
        messages.success(self.request, "Le paiement a été mis à jour.")
        return reponse


class PaymentDeleteView(StaffRoleRequiredMixin, DeleteView):
    model = Paiement
    template_name = "administration/confirm_delete.html"
    success_url = reverse_lazy("administration:payments")

    def form_valid(self, form):
        if self.object.demandes_inscription.exists():
            messages.error(self.request, "Ce paiement justifie une inscription et ne peut pas être supprimé.")
            return redirect("administration:payments")
        _notifier_dossier_etudiant(
            self.object,
            "Paiement retiré de votre dossier",
            f"Le paiement de {self.object.montant} € a été retiré de votre dossier.",
            reverse("etudiant:payments"),
        )
        messages.success(self.request, "Le paiement a été supprimé.")
        return super().form_valid(form)


class CourseListView(StaffRoleRequiredMixin, ListView):
    model = Cours
    template_name = "administration/courses.html"
    context_object_name = "cours_list"
    paginate_by = 30

    def get_queryset(self):
        # Le tri est posé ici et non laissé au Meta du modèle : l'annotation
        # ajoute un GROUP BY qui neutralise l'ordre par défaut, et une liste
        # paginée sans ordre stable répète ou omet des lignes entre deux pages.
        queryset = (
            Cours.objects.select_related("discipline")
            .prefetch_related("parcours")
            .annotate(nombre_sessions=Count("sessions", distinct=True))
            .order_by("discipline__nom", "titre")
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


class CourseCreateView(StaffRoleRequiredMixin, CreateView):
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


class CourseUpdateView(StaffRoleRequiredMixin, UpdateView):
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


class CourseDeleteView(StaffRoleRequiredMixin, DeleteView):
    model = Cours
    template_name = "administration/confirm_delete.html"
    success_url = reverse_lazy("administration:courses")

    def form_valid(self, form):
        if self.object.sessions.exists():
            messages.error(self.request, "Ce cours a déjà été programmé : désactivez-le au lieu de le supprimer.")
            return redirect("administration:courses")
        return super().form_valid(form)


# ══════════════════════════════════════════════
# Disciplines et parcours
# ══════════════════════════════════════════════


class _EcranReferentielFormation(StaffRoleRequiredMixin):
    """Les deux référentiels se tiennent depuis la page « Formations »."""

    template_name = "administration/form.html"
    success_url = reverse_lazy("administration:formations")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({"nav": "formations", "cancel_url": reverse("administration:formations")})
        return context


class DisciplineCreateView(_EcranReferentielFormation, CreateView):
    model = Discipline
    form_class = AdminDisciplineForm

    def get_context_data(self, **kwargs):
        return {**super().get_context_data(**kwargs), "form_title": "Créer une discipline"}

    def form_valid(self, form):
        messages.success(self.request, "La discipline a été créée.")
        return super().form_valid(form)


class DisciplineUpdateView(_EcranReferentielFormation, UpdateView):
    model = Discipline
    form_class = AdminDisciplineForm

    def get_context_data(self, **kwargs):
        return {**super().get_context_data(**kwargs), "form_title": f"Modifier — {self.object.nom}"}

    def form_valid(self, form):
        messages.success(self.request, "La discipline a été mise à jour.")
        return super().form_valid(form)


class DisciplineDeleteView(SuppressionProtegee, StaffRoleRequiredMixin, DeleteView):
    """« Cours.discipline » est en PROTECT : sans explication, l'erreur serait opaque."""

    model = Discipline
    template_name = "administration/confirm_delete.html"
    success_url = reverse_lazy("administration:formations")
    url_retour = "administration:formations"

    def libelle(self):
        return f"la discipline « {self.object.nom} »"

    def raison_de_bloquer(self):
        nombre = self.object.cours.count()
        if nombre:
            return (
                f"Cette discipline porte {nombre} cours : rattachez-les d'abord à une autre "
                "discipline, sinon tout le référentiel perdrait son classement."
            )
        return ""

    def get_context_data(self, **kwargs):
        return {**super().get_context_data(**kwargs), "nav": "formations"}


class ParcoursCreateView(_EcranReferentielFormation, CreateView):
    model = Parcours
    form_class = AdminParcoursForm

    def get_context_data(self, **kwargs):
        return {**super().get_context_data(**kwargs), "form_title": "Créer un parcours"}

    def form_valid(self, form):
        messages.success(self.request, "Le parcours a été créé.")
        return super().form_valid(form)


class ParcoursUpdateView(_EcranReferentielFormation, UpdateView):
    model = Parcours
    form_class = AdminParcoursForm

    def get_context_data(self, **kwargs):
        return {**super().get_context_data(**kwargs), "form_title": f"Modifier — {self.object.nom}"}

    def form_valid(self, form):
        messages.success(self.request, "Le parcours a été mis à jour.")
        return super().form_valid(form)


class ParcoursDeleteView(SuppressionProtegee, StaffRoleRequiredMixin, DeleteView):
    """Un parcours suivi par un étudiant est son diplôme : il se désactive, il ne s'efface pas."""

    model = Parcours
    template_name = "administration/confirm_delete.html"
    success_url = reverse_lazy("administration:formations")
    url_retour = "administration:formations"

    def libelle(self):
        return f"le parcours « {self.object.nom} »"

    def raison_de_bloquer(self):
        if self.object.etudiants.exists():
            return "Des étudiants suivent ce parcours : décochez « actif » plutôt que de supprimer."
        if self.object.promotions.exists():
            return "Des promotions reposent sur ce parcours : décochez « actif » plutôt que de supprimer."
        return ""

    def get_context_data(self, **kwargs):
        return {**super().get_context_data(**kwargs), "nav": "formations"}


# ══════════════════════════════════════════════
# Promotions
# ══════════════════════════════════════════════


class PromotionListView(StaffRoleRequiredMixin, ListView):
    model = Promotion
    template_name = "administration/promotions.html"
    context_object_name = "promotions"
    paginate_by = 25

    def get_queryset(self):
        queryset = (
            Promotion.objects.select_related("parcours")
            .annotate(nombre_etudiants=Count("etudiants", distinct=True))
            .order_by("-annee_debut", "nom")
        )
        recherche = self.request.GET.get("q", "").strip()
        if recherche:
            queryset = queryset.filter(Q(nom__icontains=recherche) | Q(parcours__nom__icontains=recherche))
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["query"] = self.request.GET.get("q", "")
        return context


class PromotionCreateView(StaffRoleRequiredMixin, CreateView):
    model = Promotion
    form_class = PromotionForm
    template_name = "administration/form.html"
    success_url = reverse_lazy("administration:promotions")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "form_title": "Créer une promotion",
                "nav": "promotions",
                "cancel_url": reverse("administration:promotions"),
            }
        )
        return context

    def form_valid(self, form):
        messages.success(self.request, "Promotion créée. Elle est désormais proposée à l'admission.")
        return super().form_valid(form)


class PromotionUpdateView(StaffRoleRequiredMixin, UpdateView):
    model = Promotion
    form_class = PromotionForm
    template_name = "administration/form.html"
    success_url = reverse_lazy("administration:promotions")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "form_title": f"Modifier — {self.object}",
                "nav": "promotions",
                "cancel_url": reverse("administration:promotions"),
            }
        )
        return context

    def form_valid(self, form):
        messages.success(self.request, "Promotion mise à jour.")
        return super().form_valid(form)


class PromotionDeleteView(StaffRoleRequiredMixin, DeleteView):
    model = Promotion
    template_name = "administration/confirm_delete.html"
    success_url = reverse_lazy("administration:promotions")

    def form_valid(self, form):
        # La clé étrangère est en PROTECT : supprimer lèverait une erreur de
        # base opaque. On explique plutôt ce qu'il faut faire.
        if self.object.etudiants.exists():
            messages.error(
                self.request,
                "Cette promotion compte des étudiants : désactivez-la au lieu de la supprimer.",
            )
            return redirect("administration:promotions")
        messages.success(self.request, "Promotion supprimée.")
        return super().form_valid(form)


# ══════════════════════════════════════════════
# Grille tarifaire
# ══════════════════════════════════════════════


class TarifListView(StaffRoleRequiredMixin, ListView):
    model = Tarif
    template_name = "administration/tarifs.html"
    context_object_name = "tarifs"

    def get_queryset(self):
        return Tarif.objects.order_by("formule", "type_membre")


class TarifCreateView(StaffRoleRequiredMixin, CreateView):
    model = Tarif
    form_class = TarifForm
    template_name = "administration/form.html"
    success_url = reverse_lazy("administration:tarifs")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {"form_title": "Ajouter un tarif", "nav": "tarifs", "cancel_url": reverse("administration:tarifs")}
        )
        return context

    def form_valid(self, form):
        messages.success(self.request, "Tarif ajouté. Il est visible sur le site public.")
        return super().form_valid(form)


class TarifUpdateView(StaffRoleRequiredMixin, UpdateView):
    model = Tarif
    form_class = TarifForm
    template_name = "administration/form.html"
    success_url = reverse_lazy("administration:tarifs")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "form_title": f"Modifier — {self.object}",
                "nav": "tarifs",
                "cancel_url": reverse("administration:tarifs"),
            }
        )
        return context

    def form_valid(self, form):
        messages.success(self.request, "Tarif mis à jour. Le site public reflète la nouvelle grille.")
        return super().form_valid(form)


class TarifDeleteView(StaffRoleRequiredMixin, DeleteView):
    model = Tarif
    template_name = "administration/confirm_delete.html"
    success_url = reverse_lazy("administration:tarifs")

    def form_valid(self, form):
        messages.success(self.request, "Tarif supprimé.")
        return super().form_valid(form)


# ══════════════════════════════════════════════
# Crédits ECTS
# ══════════════════════════════════════════════


class CreditECTSListView(StaffRoleRequiredMixin, ListView):
    """
    Les crédits ITEAG arrivent seuls à la publication des notes ; cet écran
    sert aux crédits FLTE et aux corrections de dossier.
    """

    model = CreditECTS
    template_name = "administration/credits_ects.html"
    context_object_name = "credits"
    paginate_by = 30

    def get_queryset(self):
        queryset = CreditECTS.objects.select_related("etudiant__utilisateur", "cours", "session").order_by(
            "-date_validation"
        )
        source = self.request.GET.get("source", "")
        recherche = self.request.GET.get("q", "").strip()
        if source:
            queryset = queryset.filter(source=source)
        if recherche:
            queryset = queryset.filter(
                Q(etudiant__utilisateur__last_name__icontains=recherche)
                | Q(etudiant__numero_etudiant__icontains=recherche)
                | Q(cours__titre__icontains=recherche)
            )
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "sources": CreditECTS.SourceCredit.choices,
                "current_source": self.request.GET.get("source", ""),
                "query": self.request.GET.get("q", ""),
            }
        )
        return context


class CreditECTSCreateView(StaffRoleRequiredMixin, CreateView):
    model = CreditECTS
    form_class = CreditECTSForm
    template_name = "administration/form.html"
    success_url = reverse_lazy("administration:credits_ects")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "form_title": "Porter un crédit au dossier",
                "nav": "credits_ects",
                "cancel_url": reverse("administration:credits_ects"),
            }
        )
        return context

    def form_valid(self, form):
        reponse = super().form_valid(form)
        _notifier_dossier_etudiant(
            self.object,
            "Crédits ECTS ajoutés",
            f"{self.object.ects_obtenus} ECTS ont été portés à votre dossier.",
            reverse("etudiant:progress"),
        )
        messages.success(self.request, "Crédit porté au dossier de l'étudiant.")
        return reponse


class CreditECTSUpdateView(StaffRoleRequiredMixin, UpdateView):
    model = CreditECTS
    form_class = CreditECTSForm
    template_name = "administration/form.html"
    success_url = reverse_lazy("administration:credits_ects")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "form_title": f"Corriger — {self.object}",
                "nav": "credits_ects",
                "cancel_url": reverse("administration:credits_ects"),
            }
        )
        return context

    def form_valid(self, form):
        reponse = super().form_valid(form)
        _notifier_dossier_etudiant(
            self.object,
            "Crédits ECTS mis à jour",
            f"Votre dossier affiche désormais {self.object.ects_obtenus} ECTS pour cet élément.",
            reverse("etudiant:progress"),
        )
        messages.success(self.request, "Crédit corrigé.")
        return reponse


class CreditECTSDeleteView(StaffRoleRequiredMixin, DeleteView):
    """
    Retirer un crédit modifie un dossier académique : réservé à
    l'administration, et tracé comme tout ce qui touche au dossier.
    """

    model = CreditECTS
    template_name = "administration/confirm_delete.html"
    success_url = reverse_lazy("administration:credits_ects")

    def form_valid(self, form):
        _notifier_dossier_etudiant(
            self.object,
            "Crédits ECTS retirés",
            f"{self.object.ects_obtenus} ECTS ont été retirés de votre dossier.",
            reverse("etudiant:progress"),
        )
        journaliser(
            "suppression",
            request=self.request,
            objet=self.object,
            objet_libelle=f"Retrait de crédit ECTS : {self.object}",
        )
        messages.success(self.request, "Crédit retiré du dossier.")
        return super().form_valid(form)


# ══════════════════════════════════════════════
# Stages — tenus par le secrétariat
# ══════════════════════════════════════════════


class _CreditAutomatiqueMixin:
    """
    Répercute la décision sur le dossier académique.

    Un stage validé ou une VAE accordée vaut des ECTS. Sans ce pont, le relevé
    de l'étudiant divergerait de la décision — c'est le défaut qui existait
    déjà entre la notation et les crédits, il ne doit pas se reproduire ici.
    Le retour en arrière est traité aussi : une décision reprise retire le
    crédit, sinon le dossier resterait crédité à tort.
    """

    champ_credit = ""

    def _repercuter(self, objet):
        from apps.academics.services import credits

        synchroniser = credits.synchroniser_stage if self.champ_credit == "stage" else credits.synchroniser_vae
        resultat = synchroniser(objet)
        if resultat == "porte":
            messages.info(self.request, "Les ECTS correspondants ont été portés au dossier de l'étudiant.")
        elif resultat == "retire":
            messages.warning(self.request, "La décision ayant changé, les ECTS ont été retirés du dossier.")


class StageListView(StaffRoleRequiredMixin, ListView):
    model = Stage
    template_name = "administration/stages.html"
    context_object_name = "stages"
    paginate_by = 25

    def get_queryset(self):
        queryset = Stage.objects.select_related("etudiant__utilisateur", "tuteur").order_by("-date_debut")
        statut = self.request.GET.get("statut", "")
        recherche = self.request.GET.get("q", "").strip()
        if statut:
            queryset = queryset.filter(statut=statut)
        if recherche:
            queryset = queryset.filter(
                Q(etudiant__utilisateur__last_name__icontains=recherche)
                | Q(etudiant__numero_etudiant__icontains=recherche)
                | Q(lieu__icontains=recherche)
                | Q(type_stage__icontains=recherche)
            )
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "statuts": Stage.StatutStage.choices,
                "current_statut": self.request.GET.get("statut", ""),
                "query": self.request.GET.get("q", ""),
            }
        )
        return context


class StageCreateView(_CreditAutomatiqueMixin, StaffRoleRequiredMixin, CreateView):
    model = Stage
    form_class = StageForm
    template_name = "administration/form.html"
    success_url = reverse_lazy("administration:stages")
    champ_credit = "stage"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "form_title": "Enregistrer un stage",
                "nav": "stages",
                "cancel_url": reverse("administration:stages"),
            }
        )
        return context

    def form_valid(self, form):
        reponse = super().form_valid(form)
        messages.success(self.request, "Stage enregistré.")
        self._repercuter(self.object)
        _notifier_dossier_etudiant(
            self.object,
            "Stage enregistré",
            f"{self.object.type_stage} — {self.object.get_statut_display()}.",
            reverse("etudiant:progress"),
        )
        return reponse


class StageUpdateView(_CreditAutomatiqueMixin, StaffRoleRequiredMixin, UpdateView):
    model = Stage
    form_class = StageForm
    template_name = "administration/form.html"
    success_url = reverse_lazy("administration:stages")
    champ_credit = "stage"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "form_title": f"Modifier — {self.object}",
                "nav": "stages",
                "cancel_url": reverse("administration:stages"),
            }
        )
        return context

    def form_valid(self, form):
        reponse = super().form_valid(form)
        messages.success(self.request, "Stage mis à jour.")
        self._repercuter(self.object)
        _notifier_dossier_etudiant(
            self.object,
            "Stage mis à jour",
            f"{self.object.type_stage} — {self.object.get_statut_display()}.",
            reverse("etudiant:progress"),
        )
        return reponse


class StageDeleteView(StaffRoleRequiredMixin, DeleteView):
    model = Stage
    template_name = "administration/confirm_delete.html"
    success_url = reverse_lazy("administration:stages")

    def form_valid(self, form):
        _notifier_dossier_etudiant(
            self.object,
            "Stage retiré de votre dossier",
            f"Le stage « {self.object.type_stage} » a été retiré de votre dossier.",
            reverse("etudiant:progress"),
        )
        journaliser(
            "suppression",
            request=self.request,
            objet=self.object,
            objet_libelle=f"Suppression de stage : {self.object}",
        )
        messages.success(self.request, "Stage supprimé.")
        return super().form_valid(form)


# ══════════════════════════════════════════════
# VAE — réservée à l'administration
# ══════════════════════════════════════════════


class VAEListView(StaffRoleRequiredMixin, ListView):
    model = VAE
    template_name = "administration/vae.html"
    context_object_name = "dossiers"
    paginate_by = 25

    def get_queryset(self):
        queryset = VAE.objects.select_related("etudiant__utilisateur").order_by("-date_soumission")
        statut = self.request.GET.get("statut", "")
        recherche = self.request.GET.get("q", "").strip()
        if statut:
            queryset = queryset.filter(statut=statut)
        if recherche:
            queryset = queryset.filter(
                Q(etudiant__utilisateur__last_name__icontains=recherche)
                | Q(etudiant__numero_etudiant__icontains=recherche)
            )
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "statuts": VAE.StatutVAE.choices,
                "current_statut": self.request.GET.get("statut", ""),
                "query": self.request.GET.get("q", ""),
            }
        )
        return context


class VAECreateView(_CreditAutomatiqueMixin, StaffRoleRequiredMixin, CreateView):
    model = VAE
    form_class = VAEForm
    template_name = "administration/form.html"
    success_url = reverse_lazy("administration:vae")
    champ_credit = "vae"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {"form_title": "Ouvrir un dossier VAE", "nav": "vae", "cancel_url": reverse("administration:vae")}
        )
        return context

    def form_valid(self, form):
        reponse = super().form_valid(form)
        messages.success(self.request, "Dossier VAE enregistré.")
        self._repercuter(self.object)
        _notifier_dossier_etudiant(
            self.object,
            "Dossier VAE enregistré",
            f"Votre demande de {self.object.ects_demandes} ECTS est au statut {self.object.get_statut_display()}.",
            reverse("etudiant:progress"),
        )
        return reponse


class VAEUpdateView(_CreditAutomatiqueMixin, StaffRoleRequiredMixin, UpdateView):
    model = VAE
    form_class = VAEForm
    template_name = "administration/form.html"
    success_url = reverse_lazy("administration:vae")
    champ_credit = "vae"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "form_title": f"Instruire — {self.object}",
                "nav": "vae",
                "cancel_url": reverse("administration:vae"),
            }
        )
        return context

    def form_valid(self, form):
        reponse = super().form_valid(form)
        journaliser(
            "modification",
            request=self.request,
            objet=self.object,
            objet_libelle=f"Décision VAE : {self.object}",
        )
        messages.success(self.request, "Dossier VAE mis à jour.")
        self._repercuter(self.object)
        _notifier_dossier_etudiant(
            self.object,
            "Dossier VAE mis à jour",
            f"Décision : {self.object.get_statut_display()} — {self.object.ects_accordes} ECTS accordés.",
            reverse("etudiant:progress"),
        )
        return reponse


class VAEDeleteView(StaffRoleRequiredMixin, DeleteView):
    model = VAE
    template_name = "administration/confirm_delete.html"
    success_url = reverse_lazy("administration:vae")

    def form_valid(self, form):
        _notifier_dossier_etudiant(
            self.object,
            "Dossier VAE retiré",
            "Le dossier VAE a été retiré de votre espace.",
            reverse("etudiant:progress"),
        )
        journaliser(
            "suppression", request=self.request, objet=self.object, objet_libelle=f"Suppression de VAE : {self.object}"
        )
        messages.success(self.request, "Dossier VAE supprimé.")
        return super().form_valid(form)


class SaisiePresenceView(StaffRoleRequiredMixin, View):
    """Saisie de l'assiduité / des présences pour un cours de session."""

    template_name = "administration/academics/saisie_presence.html"

    def get(self, request, pk):
        cours_session = get_object_or_404(
            CoursDeSession.objects.select_related("cours", "session", "enseignant"), pk=pk
        )
        inscriptions = cours_session.inscriptions.select_related(
            "etudiant__utilisateur", "etudiant__parcours"
        ).order_by("etudiant__utilisateur__last_name", "etudiant__utilisateur__first_name")

        presences_existantes = {p.etudiant_id: p for p in PresenceEtudiant.objects.filter(cours_session=cours_session)}

        liste_etudiants = []
        for insc in inscriptions:
            p = presences_existantes.get(insc.etudiant_id)
            liste_etudiants.append(
                {
                    "etudiant": insc.etudiant,
                    "statut": p.statut if p else PresenceEtudiant.Statut.PRESENT,
                    "commentaire": p.commentaire if p else "",
                }
            )

        return render(
            request,
            self.template_name,
            {
                "cours_session": cours_session,
                "liste_etudiants": liste_etudiants,
                "statut_choices": PresenceEtudiant.Statut.choices,
                "total_inscrits": inscriptions.count(),
                "nav": "sessions",
            },
        )

    def post(self, request, pk):
        cours_session = get_object_or_404(CoursDeSession, pk=pk)
        inscriptions = cours_session.inscriptions.select_related("etudiant")

        for insc in inscriptions:
            et_id = insc.etudiant_id
            statut = request.POST.get(f"statut_{et_id}")
            commentaire = request.POST.get(f"commentaire_{et_id}", "").strip()

            if statut in dict(PresenceEtudiant.Statut.choices):
                PresenceEtudiant.objects.update_or_create(
                    cours_session=cours_session,
                    etudiant_id=et_id,
                    defaults={
                        "statut": statut,
                        "commentaire": commentaire,
                        "saisi_par": request.user,
                    },
                )

        journaliser(
            "modification",
            request=request,
            objet=cours_session,
            objet_libelle=f"Saisie d'assiduité pour le cours : {cours_session}",
        )
        messages.success(request, "L'assiduité des étudiants a été enregistrée avec succès.")
        return redirect(reverse("administration:cours_session_presences", kwargs={"pk": pk}))


class PVDeliberationPDFView(StaffRoleRequiredMixin, View):
    """Génération du Procès-Verbal (PV) de délibération de session académique."""

    template_name = "administration/pdf/pv_deliberation.html"

    def get(self, request, pk):
        session = get_object_or_404(SessionAcademique, pk=pk)
        cours_sessions = session.cours_de_session.select_related("cours", "enseignant").order_by("cours__titre")

        inscriptions = (
            InscriptionSession.objects.filter(cours_session__session=session)
            .select_related("etudiant__utilisateur", "etudiant__parcours", "cours_session__cours")
            .order_by("etudiant__utilisateur__last_name", "etudiant__utilisateur__first_name")
        )

        from apps.lms.models import Evaluation

        etudiants_dict = {}
        for insc in inscriptions:
            et_id = insc.etudiant_id
            if et_id not in etudiants_dict:
                etudiants_dict[et_id] = {
                    "profil": insc.etudiant,
                    "cours_notes": [],
                    "total_ects_session": 0,
                    "reussite": True,
                }

            eval_obj = Evaluation.objects.filter(etudiant=insc.etudiant, cours_session=insc.cours_session).first()

            note_valeur = eval_obj.note if (eval_obj and eval_obj.note is not None) else None
            statut_eval = eval_obj.get_statut_display() if eval_obj else "Non noté"
            ects = eval_obj.ects_valides if eval_obj else 0

            if note_valeur is not None and note_valeur < 10:
                etudiants_dict[et_id]["reussite"] = False

            etudiants_dict[et_id]["cours_notes"].append(
                {
                    "cours": insc.cours_session.cours,
                    "note": note_valeur,
                    "statut": statut_eval,
                    "ects": ects,
                }
            )
            etudiants_dict[et_id]["total_ects_session"] += ects

        contexte = {
            "session": session,
            "cours_sessions": cours_sessions,
            "etudiants": list(etudiants_dict.values()),
            "date_edition": timezone.now(),
            "signataire": request.user,
        }

        filename = f"pv-deliberation-{slugify(session.nom)}-{session.annee_academique}.pdf"
        from apps.core.services.pdf import contexte_marque, rendre_pdf

        pdf_bytes = rendre_pdf(self.template_name, contexte_marque(**contexte))

        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename="{filename}"'
        return response
