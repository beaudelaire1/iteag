"""
Accueil unifié de l'espace enseignant.

L'enseignant avait deux tableaux de bord : l'un pour le présentiel, l'autre
pour la vidéo, aucun ne montrant l'autre. Le découpage suivait nos applications
internes — un enseignant, lui, ne pense pas « présentiel » et « vidéo », il
pense « mes enseignements ».

Comme pour l'espace étudiant, la séparation n'était pas un choix ergonomique
mais une conséquence de l'architecture : « lms » n'a pas le droit de dépendre
d'« elearning », ni l'inverse. Un portail, lui, agrège — c'est sa raison d'être.
"""

from django.db.models import Count, Q
from django.utils import timezone
from django.views.generic import TemplateView

from apps.core.mixins import TeacherRoleRequiredMixin


class AccueilEnseignantView(TeacherRoleRequiredMixin, TemplateView):
    """Une seule porte d'entrée, quel que soit le mode d'enseignement."""

    template_name = "enseignant/accueil.html"

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        professeur = getattr(self.request.user, "profil_professeur", None)
        contexte["professeur"] = professeur

        if professeur is None:
            # Un compte enseignant sans fiche : la page doit rester lisible et
            # dire quoi faire, plutôt que d'afficher des compteurs à zéro.
            contexte["sans_fiche"] = True
            return contexte

        contexte.update(self._presentiel(professeur))
        contexte.update(self._video(professeur))
        return contexte

    def _presentiel(self, professeur) -> dict:
        from apps.academics.models import CoursDeSession
        from apps.lms.models import Annonce, Evaluation, RessourcePedagogique

        aujourd_hui = timezone.localdate()
        cours = (
            CoursDeSession.objects.filter(enseignant=professeur)
            .select_related("cours", "session")
            .annotate(
                nombre_inscrits=Count("inscriptions", distinct=True),
                a_corriger=Count(
                    "evaluations",
                    filter=Q(evaluations__statut=Evaluation.StatutEvaluation.SOUMIS),
                    distinct=True,
                ),
            )
            .order_by("session__date_debut")
        )
        return {
            "cours_a_venir": [c for c in cours if c.session.date_fin >= aujourd_hui][:5],
            "cours_total": len(cours),
            "etudiants_suivis": sum(c.nombre_inscrits for c in cours),
            "evaluations_a_corriger": sum(c.a_corriger for c in cours),
            "annonces_recentes": Annonce.objects.filter(cours_session__enseignant=professeur)
            .select_related("cours_session__cours")
            .order_by("-created_at")[:4],
            "ressources_deposees": RessourcePedagogique.objects.filter(cours_session__enseignant=professeur).count(),
        }

    def _video(self, professeur) -> dict:
        from apps.elearning.models import InscriptionModule, ModuleFormation, VideoAsset

        modules = (
            ModuleFormation.objects.filter(responsable=professeur)
            .select_related("discipline")
            .annotate(nombre_inscrits=Count("inscriptions", distinct=True))
            .order_by("-updated_at")
        )
        return {
            "modules_recents": modules[:5],
            "modules_total": modules.count(),
            "modules_publies": modules.filter(statut=ModuleFormation.StatutPublication.PUBLIE).count(),
            "modules_brouillons": modules.filter(statut=ModuleFormation.StatutPublication.BROUILLON).count(),
            "apprenants_video": InscriptionModule.objects.filter(module__responsable=professeur)
            .filter(statut=InscriptionModule.StatutAcces.ACTIF)
            .count(),
            # Une vidéo restée en préparation bloque la publication d'un module :
            # c'est le premier incident du manuel d'exploitation, il doit se voir.
            "videos_en_attente": VideoAsset.objects.filter(uploade_par=self.request.user)
            .exclude(statut_traitement=VideoAsset.StatutTraitement.PRET)
            .count(),
        }
