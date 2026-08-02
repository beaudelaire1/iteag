"""
Portail enseignant — le travail demandé, sa correction, et ceux qui le rendent.

Séparé de `views.py` comme l'administration sépare ses écrans : ce module ne
traite que du devoir, de son suivi et du recours sur une note. Les vues de
cours, d'annonces et de ressources restent où elles étaient.
"""

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Count, Prefetch, Q
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views import View
from django.views.generic import CreateView, DetailView, FormView, ListView, UpdateView
from django.views.generic.detail import SingleObjectMixin

from apps.academics.models import CoursDeSession, InscriptionSession
from apps.core.mixins import TeacherRoleRequiredMixin
from apps.lms import services
from apps.lms.forms import DevoirForm, RevisionNoteForm
from apps.lms.models import Devoir, Evaluation
from apps.lms.views import _get_professeur, _teacher_courses

# ──────────────────────────────────────────────
# Devoirs
# ──────────────────────────────────────────────


class TeacherDevoirsListView(TeacherRoleRequiredMixin, ListView):
    """« Mes devoirs » — l'écran qui manquait pour savoir où l'on en est.

    Chaque ligne porte les trois nombres qui décident de la journée d'un
    enseignant : combien ont remis, combien restent à corriger, combien
    manquent encore. Ils sont annotés en une requête plutôt que comptés ligne
    par ligne — sans quoi le coût de la page croîtrait avec le nombre de
    devoirs affichés.
    """

    template_name = "lms/devoirs_list.html"
    context_object_name = "devoirs"
    paginate_by = 20

    def get_queryset(self):
        professeur = _get_professeur(self.request)
        if professeur is None:
            return Devoir.objects.none()

        a_corriger = Q(
            copies__statut__in=[Evaluation.StatutEvaluation.SOUMIS, Evaluation.StatutEvaluation.EN_CORRECTION]
        )
        corrigees = Q(copies__statut__in=[Evaluation.StatutEvaluation.NOTE, Evaluation.StatutEvaluation.PUBLIE])
        requete = (
            Devoir.objects.filter(cours_session__enseignant=professeur)
            .select_related("cours_session__cours", "cours_session__session")
            .annotate(
                nb_copies=Count("copies", distinct=True),
                nb_a_corriger=Count("copies", filter=a_corriger, distinct=True),
                nb_corrigees=Count("copies", filter=corrigees, distinct=True),
            )
        )

        etat = self.request.GET.get("etat", "")
        if etat == "a_corriger":
            requete = requete.filter(a_corriger)
        elif etat == "ouverts":
            maintenant = timezone.now()
            requete = requete.filter(
                statut=Devoir.Statut.PUBLIE,
                date_ouverture__lte=maintenant,
                date_fermeture__gte=maintenant,
            )
        elif etat:
            requete = requete.filter(statut=etat)
        return requete.distinct().order_by("-date_fermeture", "-created_at")

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        contexte.update(
            {
                "professeur": _get_professeur(self.request),
                "etat_courant": self.request.GET.get("etat", ""),
                "statut_choices": Devoir.Statut.choices,
                "cours_enseignes": _teacher_courses(self.request),
                "maintenant": timezone.now(),
            }
        )
        return contexte


class _DevoirDuProfesseur(TeacherRoleRequiredMixin):
    """Un enseignant ne voit et ne modifie que les devoirs de ses propres cours."""

    def get_queryset(self):
        professeur = _get_professeur(self.request)
        if professeur is None:
            return Devoir.objects.none()
        return Devoir.objects.filter(cours_session__enseignant=professeur).select_related(
            "cours_session__cours", "cours_session__session"
        )


class TeacherDevoirCreateView(TeacherRoleRequiredMixin, CreateView):
    """Création d'un devoir pour l'un des cours de l'enseignant.

    Le cours se désigne indifféremment dans le chemin — lien depuis la fiche du
    cours — ou en paramètre, ce qui permet à la liste des devoirs de proposer un
    simple formulaire GET plutôt qu'un panneau flottant : celui-ci sortait de
    l'écran, et n'aurait pu être refermé qu'avec du script, que la politique de
    sécurité de production interdit.
    """

    form_class = DevoirForm
    template_name = "lms/devoir_form.html"

    def dispatch(self, request, *args, **kwargs):
        identifiant = kwargs.get("cours_pk") or request.GET.get("cours")
        self.cours_session = get_object_or_404(_teacher_courses(request), pk=identifiant)
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        # Le formulaire restreint ses listes de destinataires à ce cours.
        return {**super().get_form_kwargs(), "cours_session": self.cours_session}

    def get_context_data(self, **kwargs):
        return {**super().get_context_data(**kwargs), "cours_session": self.cours_session}

    def form_valid(self, form):
        devoir = form.save(commit=False)
        devoir.cours_session = self.cours_session
        devoir.save()
        messages.success(
            self.request,
            "Devoir enregistré en brouillon. Il ne sera visible des étudiants qu'une fois ouvert.",
        )
        return redirect("lms:devoir_detail", pk=devoir.pk)


class TeacherDevoirUpdateView(_DevoirDuProfesseur, UpdateView):
    form_class = DevoirForm
    template_name = "lms/devoir_form.html"
    context_object_name = "devoir"

    def get_form_kwargs(self):
        return {**super().get_form_kwargs(), "cours_session": self.object.cours_session}

    def get_context_data(self, **kwargs):
        return {**super().get_context_data(**kwargs), "cours_session": self.object.cours_session}

    def form_valid(self, form):
        form.save()
        messages.success(self.request, "Devoir mis à jour.")
        return redirect("lms:devoir_detail", pk=self.object.pk)


class TeacherDevoirDetailView(_DevoirDuProfesseur, DetailView):
    """Suivi copie par copie : qui a remis, qui est en retard, qui manque."""

    template_name = "lms/devoir_detail.html"
    context_object_name = "devoir"

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        copies = list(
            self.object.copies.select_related("etudiant__utilisateur").order_by(
                "etudiant__utilisateur__last_name", "etudiant__utilisateur__first_name"
            )
        )
        en_attente = Evaluation.StatutEvaluation.EN_ATTENTE
        a_corriger = (Evaluation.StatutEvaluation.SOUMIS, Evaluation.StatutEvaluation.EN_CORRECTION)
        corrigees = (Evaluation.StatutEvaluation.NOTE, Evaluation.StatutEvaluation.PUBLIE)

        contexte.update(
            {
                "copies": copies,
                "attendues": [copie for copie in copies if copie.statut == en_attente],
                "a_corriger": [copie for copie in copies if copie.statut in a_corriger],
                "corrigees": [copie for copie in copies if copie.statut in corrigees],
                "tardives": [copie for copie in copies if copie.depot_tardif],
            }
        )
        return contexte


class TeacherDevoirActionView(_DevoirDuProfesseur, SingleObjectMixin, View):
    """Ouverture du devoir aux étudiants, ou clôture du dépôt."""

    http_method_names = ["post"]

    def post(self, request, *args, **kwargs):
        devoir = self.get_object()
        action = request.POST.get("action")
        try:
            if action == "publier":
                services.publier_devoir(devoir, par=request.user)
                messages.success(request, f"« {devoir.titre} » est ouvert : les étudiants en sont avertis.")
            elif action == "clore":
                services.clore_devoir(devoir, par=request.user)
                messages.success(request, f"« {devoir.titre} » est clos.")
            else:
                messages.error(request, "Action inconnue.")
        except ValidationError as erreur:
            messages.error(request, erreur.messages[0])
        return redirect("lms:devoir_detail", pk=devoir.pk)


class TeacherDelaiView(TeacherRoleRequiredMixin, SingleObjectMixin, View):
    """Délai accordé à un étudiant en particulier, sans toucher au devoir."""

    http_method_names = ["post"]

    def get_queryset(self):
        professeur = _get_professeur(self.request)
        if professeur is None:
            return Evaluation.objects.none()
        return Evaluation.objects.filter(cours_session__enseignant=professeur).select_related(
            "devoir", "etudiant__utilisateur"
        )

    def post(self, request, *args, **kwargs):
        evaluation = self.get_object()
        jusqu_au = parse_datetime(request.POST.get("jusqu_au", ""))

        if jusqu_au is None:
            messages.error(request, "Date de délai illisible.")
        else:
            if timezone.is_naive(jusqu_au):
                jusqu_au = timezone.make_aware(jusqu_au)
            try:
                services.accorder_delai(evaluation, jusqu_au=jusqu_au, par=request.user)
                messages.success(request, f"Délai accordé à {evaluation.etudiant.utilisateur.get_full_name()}.")
            except ValidationError as erreur:
                messages.error(request, erreur.messages[0])

        if evaluation.devoir_id:
            return redirect("lms:devoir_detail", pk=evaluation.devoir_id)
        return redirect("lms:evaluations_list")


# ──────────────────────────────────────────────
# Recours sur une note publiée
# ──────────────────────────────────────────────


class TeacherReviseGradeView(TeacherRoleRequiredMixin, FormView):
    """Corriger une note publiée, motif à l'appui.

    Séparée de la saisie initiale à dessein. Réviser n'est pas noter : cela
    demande une justification, laisse une trace, et prévient l'étudiant.
    """

    form_class = RevisionNoteForm
    template_name = "lms/revision_form.html"

    def dispatch(self, request, *args, **kwargs):
        professeur = _get_professeur(request)
        publiees = (
            Evaluation.objects.filter(
                cours_session__enseignant=professeur,
                statut=Evaluation.StatutEvaluation.PUBLIE,
            ).select_related("etudiant__utilisateur", "cours_session__cours", "devoir")
            if professeur is not None
            else Evaluation.objects.none()
        )
        self.evaluation = get_object_or_404(publiees, pk=kwargs["pk"])
        return super().dispatch(request, *args, **kwargs)

    def get_initial(self):
        return {"note": self.evaluation.note, "appreciation": self.evaluation.appreciation}

    def get_context_data(self, **kwargs):
        return {
            **super().get_context_data(**kwargs),
            "evaluation": self.evaluation,
            "revisions": self.evaluation.revisions.select_related("auteur"),
        }

    def form_valid(self, form):
        try:
            services.reviser(
                self.evaluation,
                note=form.cleaned_data["note"],
                appreciation=form.cleaned_data["appreciation"] or None,
                motif=form.cleaned_data["motif"],
                par=self.request.user,
            )
        except ValidationError as erreur:
            form.add_error(None, erreur.messages[0])
            return self.form_invalid(form)

        messages.success(self.request, "Note révisée. L'étudiant en est averti, et la trace est conservée.")
        return redirect("lms:course_detail", pk=self.evaluation.cours_session_id)


# ──────────────────────────────────────────────
# Mes étudiants
# ──────────────────────────────────────────────


class TeacherEtudiantsListView(TeacherRoleRequiredMixin, ListView):
    """Les étudiants inscrits aux cours de l'enseignant, et comment les joindre.

    Ne sont exposées que les coordonnées nécessaires à l'échange pédagogique —
    nom, adresse électronique, téléphone, promotion. Ni adresse postale, ni
    dossier financier, ni statut administratif : ils relèvent du secrétariat, et
    un enseignant n'a pas à en connaître pour animer son cours.
    """

    template_name = "lms/etudiants_list.html"
    context_object_name = "etudiants"
    paginate_by = 40

    def get_queryset(self):
        from apps.academics.models import ProfilEtudiant

        professeur = _get_professeur(self.request)
        if professeur is None:
            return ProfilEtudiant.objects.none()

        # Les inscriptions préchargées sont restreintes aux cours de cet
        # enseignant : la liste doit dire « dans lesquels de MES cours il est
        # inscrit », et non exposer toute la scolarité de l'étudiant, qui
        # relève du secrétariat.
        inscriptions_du_professeur = Prefetch(
            "inscriptions",
            queryset=InscriptionSession.objects.filter(cours_session__enseignant=professeur)
            .select_related("cours_session__cours", "cours_session__session")
            .order_by("cours_session__session__date_debut"),
            to_attr="inscriptions_chez_moi",
        )
        requete = (
            ProfilEtudiant.objects.filter(inscriptions__cours_session__enseignant=professeur)
            .select_related("utilisateur", "promotion", "parcours")
            .prefetch_related(inscriptions_du_professeur)
            .distinct()
            .order_by("utilisateur__last_name", "utilisateur__first_name")
        )

        cours = self.request.GET.get("cours", "")
        recherche = self.request.GET.get("q", "").strip()
        if cours:
            requete = requete.filter(inscriptions__cours_session_id=cours)
        if recherche:
            requete = requete.filter(
                Q(utilisateur__last_name__icontains=recherche)
                | Q(utilisateur__first_name__icontains=recherche)
                | Q(numero_etudiant__icontains=recherche)
            )
        return requete

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        professeur = _get_professeur(self.request)
        contexte.update(
            {
                "professeur": professeur,
                "cours_enseignes": (
                    CoursDeSession.objects.filter(enseignant=professeur).select_related("cours", "session")
                    if professeur is not None
                    else CoursDeSession.objects.none()
                ),
                "current_cours": self.request.GET.get("cours", ""),
                "query": self.request.GET.get("q", ""),
            }
        )
        return contexte
