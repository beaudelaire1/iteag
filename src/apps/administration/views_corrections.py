"""
Suivi des corrections par le secrétariat.

Une copie remise et jamais notée n'alertait personne. L'enseignant la voyait
dans son propre tableau, l'étudiant attendait sans rien savoir, et le
secrétariat — qui est celui à qui l'on vient se plaindre — n'avait aucun moyen
de constater le retard ni de relancer.

Deux principes tiennent cet écran :

- **le retard reste interne.** L'étudiant n'est jamais informé que sa copie
  traîne : le lui dire l'inquiéterait sans rien lui permettre de faire, et
  transformerait un rappel confraternel en réclamation ;
- **la relance part d'un geste,** jamais d'une horloge. Un rappel automatique
  finit par être ignoré comme le sont les alertes qui arrivent seules ; la
  secrétaire, elle, choisit qui relancer et quand.
"""

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import ListView

from apps.core.mixins import StaffRoleRequiredMixin
from apps.core.models import JournalAudit, Notification
from apps.core.services.audit import journaliser
from apps.core.services.notifications import notifier
from apps.lms.models import Evaluation


class CorrectionsView(StaffRoleRequiredMixin, ListView):
    """Copies remises en attente de note, les plus anciennes d'abord."""

    template_name = "administration/corrections.html"
    context_object_name = "copies"
    paginate_by = 50

    def get_queryset(self):
        requete = (
            Evaluation.objects.filter(
                date_soumission__isnull=False,
                statut__in=[
                    Evaluation.StatutEvaluation.SOUMIS,
                    Evaluation.StatutEvaluation.EN_CORRECTION,
                ],
            )
            .select_related(
                "etudiant__utilisateur",
                "cours_session__cours",
                "cours_session__session",
                "cours_session__enseignant__user",
            )
            .order_by("date_soumission")
        )
        if self.request.GET.get("etat") == "retard":
            # Le filtre s'applique en Python : le retard dépend du délai porté
            # par le cours, et l'exprimer en SQL demanderait de recopier ici la
            # règle qui vit sur le modèle — deux définitions à tenir d'accord.
            return [copie for copie in requete if copie.correction_en_retard()]
        return requete

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        maintenant = timezone.now()
        contexte["nav"] = "corrections"
        contexte["etat"] = self.request.GET.get("etat", "")
        contexte["maintenant"] = maintenant
        contexte["nb_en_retard"] = sum(
            1
            for copie in Evaluation.objects.filter(
                date_soumission__isnull=False,
                statut__in=[
                    Evaluation.StatutEvaluation.SOUMIS,
                    Evaluation.StatutEvaluation.EN_CORRECTION,
                ],
            ).select_related("cours_session")
            if copie.correction_en_retard(maintenant)
        )
        return contexte


class RelanceCorrectionView(StaffRoleRequiredMixin, View):
    """Rappelle à un enseignant qu'une copie attend sa note."""

    http_method_names = ["post"]

    def post(self, request, pk):
        copie = get_object_or_404(
            Evaluation.objects.select_related(
                "etudiant__utilisateur",
                "cours_session__cours",
                "cours_session__enseignant__user",
            ),
            pk=pk,
        )

        if not copie.attend_sa_correction:
            messages.error(request, "Cette copie est déjà corrigée : il n'y a plus rien à relancer.")
            return redirect(reverse("administration:corrections"))

        destinataire = getattr(copie.cours_session.enseignant, "user", None)
        if destinataire is None:
            messages.error(
                request,
                f"{copie.cours_session.enseignant} n'a pas de compte : prévenez-le autrement.",
            )
            return redirect(reverse("administration:corrections"))

        jours = copie.jours_depuis_remise()
        notifier(
            destinataire,
            f"Copie en attente de correction — {copie.cours_session.cours.titre}",
            type_notification=Notification.Type.SYSTEME,
            message=(
                f"La copie de {copie.etudiant} attend sa note depuis {jours} jour(s). "
                "L'étudiant patiente sans avoir été prévenu de ce délai."
            ),
            details=[
                {"libelle": "Cours", "valeur": copie.cours_session.cours.titre},
                {"libelle": "Étudiant", "valeur": str(copie.etudiant)},
                {"libelle": "Remise", "valeur": f"il y a {jours} jour(s)"},
            ],
            url_cible=reverse("lms:devoirs_list"),
        )
        journaliser(
            JournalAudit.Action.MODIFICATION,
            request=request,
            objet=copie,
            objet_libelle=f"Relance de {copie.cours_session.enseignant} pour la copie de {copie.etudiant}",
        )
        messages.success(request, f"{copie.cours_session.enseignant} a été relancé.")
        return redirect(reverse("administration:corrections"))
