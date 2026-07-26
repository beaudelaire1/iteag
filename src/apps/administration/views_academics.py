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

from apps.academics.models import (
    VAE,
    CoursDeSession,
    CreditECTS,
    DemandeInscriptionCours,
    Paiement,
    Promotion,
    SessionAcademique,
    Stage,
)
from apps.academics.services.inscriptions import traiter_demande
from apps.core.mixins import AdminRoleRequiredMixin, StaffRoleRequiredMixin
from apps.core.services.audit import journaliser
from apps.formations.models import Cours, Discipline, Tarif

from .forms import (
    AdminCoursForm,
    CoursDeSessionForm,
    CreditECTSForm,
    EnrollmentDecisionForm,
    PaiementForm,
    PromotionForm,
    StageForm,
    TarifForm,
    VAEForm,
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


class PromotionDeleteView(AdminRoleRequiredMixin, DeleteView):
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


class TarifCreateView(AdminRoleRequiredMixin, CreateView):
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


class TarifUpdateView(AdminRoleRequiredMixin, UpdateView):
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


class TarifDeleteView(AdminRoleRequiredMixin, DeleteView):
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
        messages.success(self.request, "Crédit porté au dossier de l'étudiant.")
        return super().form_valid(form)


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
        messages.success(self.request, "Crédit corrigé.")
        return super().form_valid(form)


class CreditECTSDeleteView(AdminRoleRequiredMixin, DeleteView):
    """
    Retirer un crédit modifie un dossier académique : réservé à
    l'administration, et tracé comme tout ce qui touche au dossier.
    """

    model = CreditECTS
    template_name = "administration/confirm_delete.html"
    success_url = reverse_lazy("administration:credits_ects")

    def form_valid(self, form):
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
        return reponse


class StageDeleteView(AdminRoleRequiredMixin, DeleteView):
    model = Stage
    template_name = "administration/confirm_delete.html"
    success_url = reverse_lazy("administration:stages")

    def form_valid(self, form):
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


class VAEListView(AdminRoleRequiredMixin, ListView):
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


class VAECreateView(_CreditAutomatiqueMixin, AdminRoleRequiredMixin, CreateView):
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
        return reponse


class VAEUpdateView(_CreditAutomatiqueMixin, AdminRoleRequiredMixin, UpdateView):
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
        return reponse


class VAEDeleteView(AdminRoleRequiredMixin, DeleteView):
    model = VAE
    template_name = "administration/confirm_delete.html"
    success_url = reverse_lazy("administration:vae")

    def form_valid(self, form):
        journaliser(
            "suppression", request=self.request, objet=self.object, objet_libelle=f"Suppression de VAE : {self.object}"
        )
        messages.success(self.request, "Dossier VAE supprimé.")
        return super().form_valid(form)
