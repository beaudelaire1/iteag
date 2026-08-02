"""Le corps enseignant vu par l'administration.

Trois gestes manquaient : ouvrir la fiche d'un enseignant sans passer par le
formulaire de modification, lui proposer un cours plutôt que le lui affecter
d'autorité, et lui confier un module e-learning.
"""

from django.contrib import messages
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import DetailView

from apps.academics.models import CoursDeSession, PropositionEnseignement
from apps.core.mixins import StaffRoleRequiredMixin
from apps.core.models import JournalAudit, Notification
from apps.core.services.audit import journaliser
from apps.core.services.notifications import notifier
from apps.elearning.models import ModuleFormation
from apps.formations.models import Professeur


class AdminProfesseurDetailView(StaffRoleRequiredMixin, DetailView):
    """Tout ce que l'administration sait d'un enseignant, sur un seul écran.

    La liste ne montrait que le nom et la spécialité, et la seule façon d'en
    savoir plus était d'ouvrir le formulaire de modification — c'est-à-dire de
    risquer une écriture pour une simple consultation.
    """

    model = Professeur
    template_name = "administration/professeur_detail.html"
    context_object_name = "professeur"

    def get_queryset(self):
        return Professeur.objects.select_related("user").prefetch_related("disciplines")

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        professeur = self.object
        aujourd_hui = timezone.localdate()

        cours = (
            CoursDeSession.objects.filter(enseignant=professeur)
            .select_related("cours", "session")
            .annotate(nombre_inscrits=Count("inscriptions", distinct=True))
            .order_by("-session__date_debut")
        )
        contexte.update(
            {
                "nav": "professeurs",
                "compte": professeur.user,
                "cours_enseignes": cours[:20],
                "cours_en_cours": [c for c in cours if c.session.date_debut <= aujourd_hui <= c.session.date_fin],
                "modules_video": ModuleFormation.objects.filter(responsable=professeur)
                .select_related("discipline")
                .order_by("-updated_at"),
                "propositions": PropositionEnseignement.objects.filter(professeur=professeur)
                .select_related("cours_session__cours", "cours_session__session")
                .order_by("-created_at")[:10],
                # Ce qu'on peut encore lui proposer : les cours qu'il n'assure
                # pas déjà, et pour lesquels aucune proposition n'est en cours.
                "cours_proposables": CoursDeSession.objects.filter(session__date_fin__gte=aujourd_hui)
                .exclude(enseignant=professeur)
                .exclude(
                    propositions__professeur=professeur,
                    propositions__statut=PropositionEnseignement.Statut.PROPOSEE,
                )
                .select_related("cours", "session")
                .order_by("session__date_debut", "cours__titre"),
                "modules_sans_responsable": ModuleFormation.objects.filter(responsable__isnull=True).order_by("titre"),
            }
        )
        return contexte


class ProposerCoursView(StaffRoleRequiredMixin, View):
    """Propose un cours à un enseignant, qui reste libre de le décliner."""

    http_method_names = ["post"]

    def post(self, request, pk):
        professeur = get_object_or_404(Professeur, pk=pk)
        cours_session = get_object_or_404(CoursDeSession, pk=request.POST.get("cours_session", 0))

        deja = PropositionEnseignement.objects.filter(
            cours_session=cours_session,
            professeur=professeur,
            statut=PropositionEnseignement.Statut.PROPOSEE,
        ).exists()
        if deja:
            messages.info(request, f"« {cours_session.cours.titre} » lui a déjà été proposé.")
            return redirect("administration:professeur_detail", pk=professeur.pk)

        PropositionEnseignement.objects.create(
            cours_session=cours_session,
            professeur=professeur,
            message=request.POST.get("message", "").strip(),
            proposee_par=request.user,
        )
        journaliser(
            JournalAudit.Action.MODIFICATION,
            utilisateur=request.user,
            request=request,
            objet=professeur,
            objet_libelle=f"Cours proposé : {cours_session.cours.titre}",
        )
        if professeur.user_id:
            notifier(
                professeur.user,
                f"Proposition d'enseignement — {cours_session.cours.titre}",
                type_notification=Notification.Type.SYSTEME,
                message=(
                    f"Session {cours_session.session.nom}. "
                    "Vous pouvez accepter ou décliner depuis votre espace enseignant."
                ),
                url_cible=reverse("enseignant:propositions"),
            )
            messages.success(request, f"Proposition envoyée à {professeur.nom_complet}, qui en est averti.")
        else:
            # Sans compte, l'enseignant ne verra jamais l'écran de réponse.
            messages.warning(
                request,
                f"Proposition enregistrée, mais {professeur.nom_complet} n'a pas de compte : prévenez-le autrement.",
            )
        return redirect("administration:professeur_detail", pk=professeur.pk)


class AssocierModuleView(StaffRoleRequiredMixin, View):
    """Confie un module e-learning à un enseignant, ou le lui retire."""

    http_method_names = ["post"]

    def post(self, request, pk):
        professeur = get_object_or_404(Professeur, pk=pk)
        module = get_object_or_404(ModuleFormation, pk=request.POST.get("module", 0))
        retirer = request.POST.get("action") == "retirer"

        if retirer:
            if module.responsable_id != professeur.pk:
                messages.error(request, "Ce module n'est pas confié à cet enseignant.")
                return redirect("administration:professeur_detail", pk=professeur.pk)
            module.responsable = None
            libelle = f"Module retiré : {module.titre}"
            message = f"« {module.titre} » ne lui est plus confié."
        else:
            module.responsable = professeur
            libelle = f"Module confié : {module.titre}"
            message = f"« {module.titre} » est confié à {professeur.nom_complet}."

        module.save(update_fields=["responsable", "updated_at"])
        journaliser(
            JournalAudit.Action.MODIFICATION,
            utilisateur=request.user,
            request=request,
            objet=professeur,
            objet_libelle=libelle,
        )
        if not retirer and professeur.user_id:
            notifier(
                professeur.user,
                f"Module confié — {module.titre}",
                type_notification=Notification.Type.NOUVEAU_MODULE,
                message="Vous en êtes désormais responsable dans l'atelier e-learning.",
                url_cible=reverse("elearning:enseignant_modules"),
            )
        messages.success(request, message)
        return redirect("administration:professeur_detail", pk=professeur.pk)


# La réponse de l'enseignant vit dans « portail_enseignant » : c'est son
# espace, et « administration » n'a pas à porter les écrans d'un autre rôle.
