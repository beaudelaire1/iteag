"""Catalogue étudiant et demandes d'inscription aux cours."""

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views import View
from django.views.generic import DetailView, ListView, TemplateView

from apps.academics.forms import EnrollmentRequestForm
from apps.academics.models import (
    CoursDeSession,
    DemandeInscriptionCours,
    InscriptionSession,
    Paiement,
    SessionAcademique,
)
from apps.academics.services.inscriptions import annuler_demande, soumettre_demande, verifier_eligibilite
from apps.core.mixins import StudentRoleRequiredMixin
from apps.formations.models import Discipline


class CourseCatalogueView(StudentRoleRequiredMixin, ListView):
    template_name = "etudiant/course_catalogue.html"
    context_object_name = "offres"
    paginate_by = 12

    def get_queryset(self):
        profil = self.request.user.profil_etudiant
        queryset = (
            CoursDeSession.objects.filter(
                cours__actif=True,
                session__date_fin__gte=timezone.localdate(),
            )
            .filter(Q(cours__parcours=profil.parcours) | Q(cours__parcours__isnull=True))
            .select_related("cours__discipline", "session", "enseignant")
            .prefetch_related("cours__parcours")
            .annotate(nombre_inscrits=Count("inscriptions", distinct=True))
            .distinct()
        )
        recherche = self.request.GET.get("q", "").strip()
        discipline = self.request.GET.get("discipline", "")
        session = self.request.GET.get("session", "")
        modalite = self.request.GET.get("modalite", "")
        if recherche:
            queryset = queryset.filter(
                Q(cours__titre__icontains=recherche)
                | Q(cours__description__icontains=recherche)
                | Q(cours__code__icontains=recherche)
                | Q(enseignant__nom__icontains=recherche)
                | Q(enseignant__prenom__icontains=recherche)
            )
        if discipline:
            queryset = queryset.filter(cours__discipline_id=discipline)
        if session:
            queryset = queryset.filter(session_id=session)
        if modalite:
            queryset = queryset.filter(modalite=modalite)
        return queryset.order_by("session__date_debut", "cours__titre")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        profil = self.request.user.profil_etudiant
        offres = list(context["offres"])
        ids = [offre.pk for offre in offres]
        demandes = {
            demande.cours_session_id: demande
            for demande in DemandeInscriptionCours.objects.filter(etudiant=profil, cours_session_id__in=ids)
        }
        inscriptions = set(
            InscriptionSession.objects.filter(etudiant=profil, cours_session_id__in=ids).values_list(
                "cours_session_id", flat=True
            )
        )
        for offre in offres:
            offre.demande_etudiant = demandes.get(offre.pk)
            offre.deja_inscrit = offre.pk in inscriptions
            offre.montant_etudiant = offre.montant_pour(profil)
            offre.motif_blocage = verifier_eligibilite(profil, offre)
        context["offres"] = offres
        context.update(
            {
                "disciplines": Discipline.objects.filter(cours__sessions__session__date_fin__gte=timezone.localdate())
                .distinct()
                .order_by("ordre", "nom"),
                "sessions": SessionAcademique.objects.filter(date_fin__gte=timezone.localdate()).order_by("date_debut"),
                "modalites": CoursDeSession.Modalite.choices,
                "query": self.request.GET.get("q", ""),
                "current_discipline": self.request.GET.get("discipline", ""),
                "current_session": self.request.GET.get("session", ""),
                "current_modalite": self.request.GET.get("modalite", ""),
                **self._modules_video(profil),
            }
        )
        return context

    def _modules_video(self, profil) -> dict:
        """Les modules vidéo relèvent du même catalogue : c'est un format, pas une offre à part.

        La recherche s'y applique aussi, sans quoi filtrer ferait disparaître la
        moitié de l'offre sans le dire.
        """
        from apps.elearning.models import InscriptionModule, ModuleFormation

        modules = (
            ModuleFormation.objects.filter(statut=ModuleFormation.StatutPublication.PUBLIE)
            .select_related("discipline", "responsable")
            .order_by("ordre", "titre")
        )
        recherche = self.request.GET.get("q", "").strip()
        discipline = self.request.GET.get("discipline", "")
        if recherche:
            modules = modules.filter(Q(titre__icontains=recherche) | Q(description__icontains=recherche))
        if discipline:
            modules = modules.filter(discipline_id=discipline)
        # Une session ou une modalité de présentiel ne s'applique pas à un module
        # vidéo : filtrer là-dessus doit masquer la section, non la fausser.
        if self.request.GET.get("session") or self.request.GET.get("modalite"):
            return {"modules_video": []}

        modules = list(modules)
        etats = {
            acces.module_id: acces for acces in InscriptionModule.objects.filter(etudiant=profil, module__in=modules)
        }
        for module in modules:
            module.acces_etudiant = etats.get(module.pk)
        return {"modules_video": modules}


class CourseOfferingDetailView(StudentRoleRequiredMixin, DetailView):
    model = CoursDeSession
    template_name = "etudiant/course_offering_detail.html"
    context_object_name = "offre"

    def get_queryset(self):
        profil = self.request.user.profil_etudiant
        return (
            CoursDeSession.objects.filter(cours__actif=True)
            .filter(Q(cours__parcours=profil.parcours) | Q(cours__parcours__isnull=True))
            .select_related("cours__discipline", "session", "enseignant")
            .prefetch_related("cours__parcours")
            .annotate(nombre_inscrits=Count("inscriptions", distinct=True))
            .distinct()
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        profil = self.request.user.profil_etudiant
        context.update(
            {
                "profil": profil,
                "demande": DemandeInscriptionCours.objects.filter(etudiant=profil, cours_session=self.object).first(),
                "deja_inscrit": InscriptionSession.objects.filter(etudiant=profil, cours_session=self.object).exists(),
                "montant": self.object.montant_pour(profil),
                "motif_blocage": verifier_eligibilite(profil, self.object),
                "form": kwargs.get("form") or EnrollmentRequestForm(),
            }
        )
        return context


class EnrollmentRequestCreateView(StudentRoleRequiredMixin, View):
    http_method_names = ["post"]

    def post(self, request, *args, **kwargs):
        profil = request.user.profil_etudiant
        offre = get_object_or_404(
            CoursDeSession.objects.select_related("cours", "session", "enseignant"),
            pk=kwargs["pk"],
            cours__actif=True,
        )
        form = EnrollmentRequestForm(request.POST, request.FILES)
        if not form.is_valid():
            for erreurs in form.errors.values():
                for erreur in erreurs:
                    messages.error(request, erreur)
            return redirect("etudiant:course_offering_detail", pk=offre.pk)
        try:
            demande = soumettre_demande(
                etudiant=profil,
                cours_session=offre,
                request=request,
                **form.cleaned_data,
            )
        except ValidationError as exc:
            messages.error(request, exc.messages[0])
        else:
            messages.success(
                request,
                f"Votre demande pour « {demande.cours_session.cours.titre} » a été transmise au secrétariat.",
            )
        return redirect("etudiant:enrollment_requests")


class MyEnrollmentRequestsView(StudentRoleRequiredMixin, ListView):
    template_name = "etudiant/enrollment_requests.html"
    context_object_name = "demandes"
    paginate_by = 20

    def get_queryset(self):
        return (
            DemandeInscriptionCours.objects.filter(etudiant=self.request.user.profil_etudiant)
            .select_related("cours_session__cours", "cours_session__session", "paiement")
            .order_by("-created_at")
        )


class EnrollmentRequestCancelView(StudentRoleRequiredMixin, View):
    http_method_names = ["post"]

    def post(self, request, *args, **kwargs):
        demande = get_object_or_404(
            DemandeInscriptionCours,
            pk=kwargs["pk"],
            etudiant=request.user.profil_etudiant,
        )
        try:
            annuler_demande(demande=demande, etudiant=request.user.profil_etudiant, request=request)
        except ValidationError as exc:
            messages.error(request, exc.messages[0])
        else:
            messages.success(request, "La demande d'inscription a été annulée.")
        return redirect("etudiant:enrollment_requests")


class StudentPaymentsView(StudentRoleRequiredMixin, TemplateView):
    template_name = "etudiant/payments.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        profil = self.request.user.profil_etudiant
        paiements = Paiement.objects.filter(etudiant=profil).select_related("session")
        context.update(
            {
                "profil": profil,
                "paiements": paiements,
                "total_confirme": sum(
                    (paiement.montant for paiement in paiements if paiement.statut == Paiement.StatutPaiement.CONFIRME),
                    start=0,
                ),
                "demandes_a_payer": profil.demandes_inscription.filter(
                    statut=DemandeInscriptionCours.Statut.PAIEMENT_ATTENTE
                ).select_related("cours_session__cours", "cours_session__session"),
            }
        )
        return context
