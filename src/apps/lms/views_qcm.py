"""
Questionnaires et groupes de travail — portail enseignant, et passage étudiant.

Le questionnaire est le seul devoir que la plateforme sait corriger seule : ses
réponses sont fermées. Les réponses de l'étudiant sont conservées telles
quelles, ce qui permet de rejouer une correction après rectification du barème
plutôt que de ressaisir chaque copie.
"""

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Count, Prefetch
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View
from django.views.generic import CreateView, DeleteView, DetailView, FormView, ListView, UpdateView

from apps.core.mixins import StudentRoleRequiredMixin, TeacherRoleRequiredMixin
from apps.lms import services
from apps.lms.forms import ChoixForm, GroupeForm, MessageGroupeForm, QuestionForm
from apps.lms.models import Choix, Devoir, Evaluation, GroupeEtudiants, Question
from apps.lms.views import _get_professeur, _teacher_courses

# ──────────────────────────────────────────────
# Construction du questionnaire
# ──────────────────────────────────────────────


class _QuestionnaireDuProfesseur(TeacherRoleRequiredMixin):
    """Le devoir visé doit appartenir à un cours de l'enseignant."""

    def devoir_ou_404(self, pk) -> Devoir:
        professeur = _get_professeur(self.request)
        if professeur is None:
            raise Devoir.DoesNotExist
        return get_object_or_404(
            Devoir.objects.filter(cours_session__enseignant=professeur).select_related("cours_session__cours"),
            pk=pk,
        )


class TeacherQuestionnaireView(_QuestionnaireDuProfesseur, DetailView):
    """L'atelier : les questions posées, leurs propositions, ce qui manque."""

    template_name = "lms/questionnaire.html"
    context_object_name = "devoir"

    def get_object(self, queryset=None):
        return self.devoir_ou_404(self.kwargs["pk"])

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        questions = list(
            self.object.questions.prefetch_related(Prefetch("choix", queryset=Choix.objects.order_by("ordre", "id")))
        )
        contexte.update(
            {
                "questions": questions,
                "total_points": sum(question.points for question in questions),
                "motif_incomplet": services.motif_qcm_incomplet(self.object),
                "form_question": QuestionForm(),
                "copies_rendues": self.object.copies.exclude(statut=Evaluation.StatutEvaluation.EN_ATTENTE).count(),
            }
        )
        return contexte


class TeacherQuestionCreateView(_QuestionnaireDuProfesseur, View):
    http_method_names = ["post"]

    def post(self, request, pk):
        devoir = self.devoir_ou_404(pk)
        form = QuestionForm(request.POST)
        if form.is_valid():
            question = form.save(commit=False)
            question.devoir = devoir
            if not question.ordre:
                question.ordre = devoir.questions.count() + 1
            question.save()
            messages.success(request, "Question ajoutée. Renseignez maintenant ses propositions.")
            return redirect("lms:question_detail", pk=question.pk)

        messages.error(request, "La question n'a pas pu être enregistrée : vérifiez l'énoncé et le barème.")
        return redirect("lms:questionnaire", pk=devoir.pk)


class TeacherQuestionDetailView(TeacherRoleRequiredMixin, DetailView):
    """Édition d'une question et de ses propositions."""

    template_name = "lms/question_detail.html"
    context_object_name = "question"

    def get_queryset(self):
        professeur = _get_professeur(self.request)
        if professeur is None:
            return Question.objects.none()
        return Question.objects.filter(devoir__cours_session__enseignant=professeur).select_related(
            "devoir__cours_session__cours"
        )

    def get_context_data(self, **kwargs):
        return {
            **super().get_context_data(**kwargs),
            "form_question": QuestionForm(instance=self.object),
            "form_choix": ChoixForm(),
            "choix": self.object.choix.all(),
            "probleme": self.object.est_valide(),
        }


class TeacherQuestionUpdateView(TeacherRoleRequiredMixin, UpdateView):
    form_class = QuestionForm
    template_name = "lms/question_detail.html"
    http_method_names = ["post"]

    def get_queryset(self):
        professeur = _get_professeur(self.request)
        if professeur is None:
            return Question.objects.none()
        return Question.objects.filter(devoir__cours_session__enseignant=professeur)

    def form_valid(self, form):
        form.save()
        messages.success(self.request, "Question mise à jour.")
        return redirect("lms:question_detail", pk=self.object.pk)

    def form_invalid(self, form):
        messages.error(self.request, "Modification refusée : vérifiez l'énoncé et le barème.")
        return redirect("lms:question_detail", pk=self.get_object().pk)


class TeacherQuestionDeleteView(TeacherRoleRequiredMixin, DeleteView):
    template_name = "lms/confirm_delete.html"
    context_object_name = "objet"

    def get_queryset(self):
        professeur = _get_professeur(self.request)
        if professeur is None:
            return Question.objects.none()
        return Question.objects.filter(devoir__cours_session__enseignant=professeur)

    def form_valid(self, form):
        self.devoir_pk = self.get_object().devoir_id
        messages.success(self.request, "Question supprimée.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("lms:questionnaire", kwargs={"pk": self.devoir_pk})


class TeacherChoixCreateView(TeacherRoleRequiredMixin, View):
    http_method_names = ["post"]

    def post(self, request, pk):
        professeur = _get_professeur(request)
        question = get_object_or_404(
            Question.objects.filter(devoir__cours_session__enseignant=professeur)
            if professeur
            else Question.objects.none(),
            pk=pk,
        )
        form = ChoixForm(request.POST)
        if form.is_valid():
            choix = form.save(commit=False)
            choix.question = question
            if not choix.ordre:
                choix.ordre = question.choix.count() + 1
            choix.save()
            messages.success(request, "Proposition ajoutée.")
        else:
            messages.error(request, "Proposition invalide : le libellé est obligatoire.")
        return redirect("lms:question_detail", pk=question.pk)


class TeacherChoixDeleteView(TeacherRoleRequiredMixin, View):
    http_method_names = ["post"]

    def post(self, request, pk):
        professeur = _get_professeur(request)
        choix = get_object_or_404(
            Choix.objects.filter(question__devoir__cours_session__enseignant=professeur)
            if professeur
            else Choix.objects.none(),
            pk=pk,
        )
        question_pk = choix.question_id
        choix.delete()
        messages.success(request, "Proposition retirée.")
        return redirect("lms:question_detail", pk=question_pk)


class TeacherRecorrigerView(_QuestionnaireDuProfesseur, View):
    """Rejoue la correction après rectification du barème."""

    http_method_names = ["post"]

    def post(self, request, pk):
        devoir = self.devoir_ou_404(pk)
        nombre = services.recorriger(devoir)
        messages.success(request, f"{nombre} copie(s) recorrigée(s) avec le barème actuel.")
        return redirect("lms:devoir_detail", pk=devoir.pk)


# ──────────────────────────────────────────────
# Passage du questionnaire par l'étudiant
# ──────────────────────────────────────────────


class StudentQuestionnaireView(StudentRoleRequiredMixin, View):
    """Le questionnaire tel que l'étudiant le voit — sans les bonnes réponses.

    La justesse d'une proposition n'est jamais rendue dans la page : elle ne
    sort de la base qu'au moment de corriger, côté serveur.
    """

    template_name = "etudiant/questionnaire.html"

    def get_evaluation(self, request, pk) -> Evaluation:
        return get_object_or_404(
            Evaluation.objects.select_related("devoir", "cours_session__cours").prefetch_related(
                "devoir__questions__choix"
            ),
            pk=pk,
            etudiant=request.user.profil_etudiant,
        )

    def get(self, request, pk):
        evaluation = self.get_evaluation(request, pk)
        return render(request, self.template_name, self._contexte(evaluation))

    def post(self, request, pk):
        evaluation = self.get_evaluation(request, pk)
        choix_par_question = {
            question.pk: [int(valeur) for valeur in request.POST.getlist(f"question-{question.pk}") if valeur.isdigit()]
            for question in evaluation.devoir.questions.all()
        }
        try:
            services.enregistrer_reponses(evaluation, choix_par_question)
        except ValidationError as erreur:
            messages.error(request, erreur.messages[0])
            return render(request, self.template_name, self._contexte(evaluation))

        messages.success(request, "Questionnaire remis. Votre note vous sera communiquée après publication.")
        return redirect("etudiant:grades")

    def _contexte(self, evaluation) -> dict:
        return {
            "evaluation": evaluation,
            "devoir": evaluation.devoir,
            "questions": evaluation.devoir.questions.prefetch_related("choix") if evaluation.devoir else [],
            "motif_de_refus": evaluation.motif_de_refus_depot(),
            "echeance": evaluation.echeance(),
        }


# ──────────────────────────────────────────────
# Groupes de travail
# ──────────────────────────────────────────────


class TeacherGroupesListView(TeacherRoleRequiredMixin, ListView):
    template_name = "lms/groupes_list.html"
    context_object_name = "groupes"

    def get_queryset(self):
        professeur = _get_professeur(self.request)
        if professeur is None:
            return GroupeEtudiants.objects.none()
        return (
            GroupeEtudiants.objects.filter(cours_session__enseignant=professeur)
            .select_related("cours_session__cours", "cours_session__session")
            .prefetch_related("membres__utilisateur")
            .annotate(nb_membres=Count("membres", distinct=True))
            .order_by("cours_session__cours__titre", "nom")
        )

    def get_context_data(self, **kwargs):
        return {
            **super().get_context_data(**kwargs),
            "professeur": _get_professeur(self.request),
            "cours_enseignes": _teacher_courses(self.request),
        }


class TeacherGroupeCreateView(TeacherRoleRequiredMixin, CreateView):
    form_class = GroupeForm
    template_name = "lms/groupe_form.html"

    def dispatch(self, request, *args, **kwargs):
        identifiant = kwargs.get("cours_pk") or request.GET.get("cours")
        self.cours_session = get_object_or_404(_teacher_courses(request), pk=identifiant)
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        return {**super().get_form_kwargs(), "cours_session": self.cours_session}

    def get_context_data(self, **kwargs):
        return {**super().get_context_data(**kwargs), "cours_session": self.cours_session}

    def form_valid(self, form):
        groupe = form.save(commit=False)
        groupe.cours_session = self.cours_session
        groupe.save()
        form.save_m2m()
        messages.success(self.request, f"Groupe « {groupe.nom} » créé.")
        return redirect("lms:groupes_list")


class TeacherGroupeUpdateView(TeacherRoleRequiredMixin, UpdateView):
    form_class = GroupeForm
    template_name = "lms/groupe_form.html"
    context_object_name = "groupe"

    def get_queryset(self):
        professeur = _get_professeur(self.request)
        if professeur is None:
            return GroupeEtudiants.objects.none()
        return GroupeEtudiants.objects.filter(cours_session__enseignant=professeur).select_related(
            "cours_session__cours"
        )

    def get_form_kwargs(self):
        return {**super().get_form_kwargs(), "cours_session": self.object.cours_session}

    def get_context_data(self, **kwargs):
        return {**super().get_context_data(**kwargs), "cours_session": self.object.cours_session}

    def form_valid(self, form):
        form.save()
        messages.success(self.request, "Groupe mis à jour.")
        return redirect("lms:groupes_list")


class TeacherGroupeDeleteView(TeacherRoleRequiredMixin, DeleteView):
    template_name = "lms/confirm_delete.html"
    context_object_name = "objet"

    def get_queryset(self):
        professeur = _get_professeur(self.request)
        if professeur is None:
            return GroupeEtudiants.objects.none()
        return GroupeEtudiants.objects.filter(cours_session__enseignant=professeur)

    def form_valid(self, form):
        messages.success(self.request, "Groupe supprimé.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("lms:groupes_list")


class TeacherGroupeMessageView(TeacherRoleRequiredMixin, FormView):
    """Un message adressé d'un coup à tous les membres du groupe."""

    form_class = MessageGroupeForm
    template_name = "lms/groupe_message.html"

    def dispatch(self, request, *args, **kwargs):
        professeur = _get_professeur(request)
        self.groupe = get_object_or_404(
            GroupeEtudiants.objects.filter(cours_session__enseignant=professeur).prefetch_related(
                "membres__utilisateur"
            )
            if professeur
            else GroupeEtudiants.objects.none(),
            pk=kwargs["pk"],
        )
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        return {**super().get_context_data(**kwargs), "groupe": self.groupe}

    def form_valid(self, form):
        envoyes = services.message_au_groupe(
            self.groupe,
            titre=form.cleaned_data["titre"],
            message=form.cleaned_data["message"],
            par=self.request.user,
        )
        if envoyes:
            messages.success(self.request, f"Message transmis à {envoyes} étudiant(s).")
        else:
            messages.warning(self.request, "Ce groupe n'a aucun membre actif : personne n'a été notifié.")
        return redirect("lms:groupes_list")
