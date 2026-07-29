"""
Vues de l'espace étudiant.

Ce portail agrège plusieurs domaines — scolarité, évaluations, documents,
formation vidéo. Il vit hors des applications de domaine pour cette raison :
logé dans « academics », il ne pouvait pas montrer la formation vidéo sans
créer une dépendance interdite, et le tableau de bord de l'étudiant ignorait
la moitié de ce à quoi il a accès.
"""

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Count, Prefetch, Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.views.generic import TemplateView, UpdateView

from apps.academics.forms import StudentSubmissionForm
from apps.academics.models import (
    CoursDeSession,
    CreditECTS,
    DemandeInscriptionCours,
    InscriptionSession,
    ProfilEtudiant,
    SessionAcademique,
)
from apps.core.mixins import StudentRoleRequiredMixin
from apps.core.models import Notification
from apps.core.services.notifications import notifier
from apps.documents.models import DocumentAdministratif
from apps.lms.models import Annonce, Evaluation, RessourcePedagogique
from apps.lms.notifications import notifier_enseignant


class StudentDashboardView(StudentRoleRequiredMixin, TemplateView):
    template_name = "etudiant/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        profil = ProfilEtudiant.objects.select_related("parcours", "promotion").get(utilisateur=self.request.user)
        total_ects_acquis = profil.total_ects_acquis
        # La propriété réutilise cette valeur dans le template au lieu de
        # relancer la même agrégation SQL.
        profil.ects_acquis_annotes = total_ects_acquis
        today = timezone.localdate()

        current_session = (
            SessionAcademique.objects.filter(
                Q(date_debut__lte=today, date_fin__gte=today) | Q(statut=SessionAcademique.StatutSession.EN_COURS)
            )
            .order_by("date_debut")
            .first()
        )
        prochaine_session = SessionAcademique.objects.filter(date_debut__gt=today).order_by("date_debut").first()
        demandes = profil.demandes_inscription.aggregate(
            en_cours=Count(
                "pk",
                filter=Q(
                    statut__in=[
                        DemandeInscriptionCours.Statut.SOUMISE,
                        DemandeInscriptionCours.Statut.PAIEMENT_ATTENTE,
                    ]
                ),
            ),
            paiement=Count(
                "pk",
                filter=Q(statut=DemandeInscriptionCours.Statut.PAIEMENT_ATTENTE),
            ),
        )

        context.update(
            {
                "profil": profil,
                "current_session": current_session,
                "prochaine_session": prochaine_session,
                "total_ects_acquis": total_ects_acquis,
                "progress_percent": round((total_ects_acquis / profil.parcours.ects_requis) * 100)
                if profil.parcours.ects_requis
                else 0,
                "pending_evaluations": profil.evaluations.select_related(
                    "cours_session__cours", "cours_session__session", "devoir"
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
                )[:6],
                "documents_count": DocumentAdministratif.objects.filter(etudiant=self.request.user).count(),
                # Formation vidéo. Absente du tableau de bord tant que ces vues
                # vivaient dans « academics », qui n'a pas le droit de dépendre
                # d'« elearning » : l'étudiant devait deviner qu'un autre écran
                # existait. C'est ce que l'extraction du portail débloque.
                **self._formation_video(profil),
                "latest_payments": profil.paiements.select_related("session")[:4],
                "demandes_en_cours": demandes["en_cours"],
                "demandes_paiement": demandes["paiement"],
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

    def _formation_video(self, profil) -> dict:
        """Modules vidéo en cours, reprise de lecture et attestations obtenues."""
        from apps.elearning.models import AttestationModule, InscriptionModule

        acces = (
            InscriptionModule.objects.filter(etudiant=profil)
            .select_related("module", "module__discipline")
            .order_by("-updated_at")
        )
        en_cours = [i for i in acces if i.statut == InscriptionModule.StatutAcces.ACTIF][:4]

        return {
            "modules_en_cours": en_cours,
            "modules_termines": sum(1 for i in acces if i.statut == InscriptionModule.StatutAcces.TERMINE),
            "modules_total": len(acces),
            "attestations": AttestationModule.objects.filter(inscription__etudiant=profil)
            .select_related("inscription__module")
            .order_by("-created_at")[:3],
        }


class StudentProgressView(StudentRoleRequiredMixin, TemplateView):
    template_name = "etudiant/progress.html"

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
    """ETU-003 — Tout ce que l'étudiant suit, quel que soit le format.

    La vidéo n'est pas une formation à part : c'est un format d'enseignement.
    Séparer les deux écrans obligeait l'étudiant à savoir d'avance où chercher
    son cours — et laissait la moitié de sa formation hors de sa navigation.
    """

    template_name = "etudiant/courses.html"

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
        context.update({"profil": profil, "inscriptions": inscriptions, **self._modules_video(profil)})
        return context

    def _modules_video(self, profil) -> dict:
        from apps.elearning.models import AttestationModule, InscriptionModule

        acces = list(
            InscriptionModule.objects.filter(etudiant=profil)
            .select_related("module", "module__discipline", "module__responsable")
            .order_by("module__ordre", "module__titre")
        )
        etats = InscriptionModule.StatutAcces
        return {
            "modules_actifs": [i for i in acces if i.statut in (etats.ACTIF, etats.TERMINE)],
            "modules_demandes": [i for i in acces if i.statut == etats.DEMANDE],
            "modules_indisponibles": [i for i in acces if i.statut in (etats.SUSPENDU, etats.EXPIRE, etats.REVOQUE)],
            "attestations_modules": AttestationModule.objects.filter(inscription__etudiant=profil)
            .select_related("inscription__module")
            .order_by("-created_at"),
        }


class StudentGradesView(StudentRoleRequiredMixin, TemplateView):
    """ETU-006 — Consultation des notes et appréciations."""

    template_name = "etudiant/grades.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        profil = self.request.user.profil_etudiant
        evaluations = (
            Evaluation.objects.filter(etudiant=profil)
            .select_related("cours_session__cours", "cours_session__session", "devoir")
            .order_by("-cours_session__session__date_debut", "cours_session__cours__titre")
        )
        published = evaluations.filter(statut=Evaluation.StatutEvaluation.PUBLIE)
        pending = evaluations.exclude(statut=Evaluation.StatutEvaluation.PUBLIE)
        context.update({"profil": profil, "published_grades": published, "pending_grades": pending})
        return context


class StudentEvaluationSubmitView(StudentRoleRequiredMixin, UpdateView):
    form_class = StudentSubmissionForm
    template_name = "etudiant/submission_form.html"
    context_object_name = "evaluation"

    def get_object(self, queryset=None):
        # Une copie déjà remise peut être remplacée tant que la fenêtre reste
        # ouverte ; le service métier tranche et fournit un message explicite.
        evaluation = get_object_or_404(
            Evaluation.objects.select_related("cours_session__cours", "cours_session__session", "devoir"),
            pk=self.kwargs["pk"],
            etudiant=self.request.user.profil_etudiant,
        )
        self.motif_fermeture = evaluation.motif_de_refus_depot()
        if not self.motif_fermeture and evaluation.devoir_id is None:
            # Compatibilité avec les évaluations créées avant les devoirs
            # détaillés : leur fenêtre reste portée par le cours.
            self.motif_fermeture = evaluation.cours_session.motif_depot_ferme
        return evaluation

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        evaluation = self.object
        contexte.update(
            {
                "devoir": evaluation.devoir,
                "echeance": evaluation.echeance() or evaluation.cours_session.depot_fermeture,
                "motif_de_refus": self.motif_fermeture,
                "motif_fermeture": self.motif_fermeture,
                "depot_ouvert": not self.motif_fermeture,
                "cours_session": evaluation.cours_session,
                "delai_accorde": evaluation.date_limite_reportee,
            }
        )
        return contexte

    def form_valid(self, form):
        if self.motif_fermeture:
            messages.error(self.request, self.motif_fermeture)
            form.add_error(None, self.motif_fermeture)
            return self.form_invalid(form)

        from apps.lms import services

        try:
            evaluation = services.deposer(self.object, form.cleaned_data["fichier_soumis"], request=self.request)
        except ValidationError as erreur:
            form.add_error(None, erreur.messages[0])
            return self.form_invalid(form)

        titre_cours = evaluation.cours_session.cours.titre
        notifier(
            self.request.user,
            f"Travail remis — {titre_cours}",
            type_notification=Notification.Type.SYSTEME,
            message="Votre dépôt est enregistré. L'enseignant peut maintenant le corriger.",
            url_cible=reverse("etudiant:grades"),
        )
        notifier_enseignant(
            evaluation.cours_session,
            f"Nouveau travail remis — {titre_cours}",
            message=f"{evaluation.etudiant} a déposé son travail.",
            url_cible=reverse("lms:evaluations_list"),
        )

        if evaluation.depot_tardif:
            messages.warning(
                self.request,
                "Votre travail a été remis après l'échéance : il est signalé comme tardif à l'enseignant.",
            )
        else:
            messages.success(self.request, "Votre travail a été remis. L'enseignant peut maintenant le corriger.")
        return redirect("etudiant:grades")
