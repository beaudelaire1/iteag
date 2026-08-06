"""Garde-fous des questionnaires dans le portail enseignant.

Le domaine QCM existe déjà dans ``lms`` : questions pondérées, propositions,
réponses conservées et note calculée automatiquement. Ce module ferme les
contournements restants sans dupliquer ces modèles.
"""

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect

from apps.lms import services
from apps.lms.forms import ChoixForm
from apps.lms.models import Choix, Devoir, Question
from apps.lms.views import _get_professeur
from apps.lms.views_devoirs import TeacherDevoirActionView
from apps.lms.views_qcm import (
    TeacherChoixCreateView,
    TeacherChoixDeleteView,
    TeacherQuestionCreateView,
    TeacherQuestionDeleteView,
    TeacherQuestionDetailView,
    TeacherQuestionnaireView,
    TeacherQuestionUpdateView,
    TeacherRecorrigerView,
)


class _DevoirQCMSeulement:
    """Refuse l'atelier QCM pour une autre modalité de devoir."""

    def devoir_ou_404(self, pk):
        devoir = super().devoir_ou_404(pk)
        if devoir.modalite != Devoir.Modalite.QCM:
            raise Http404("Ce devoir n'est pas un questionnaire.")
        return devoir


class TeacherQuestionnaireQCMView(_DevoirQCMSeulement, TeacherQuestionnaireView):
    pass


class TeacherQuestionCreateQCMView(_DevoirQCMSeulement, TeacherQuestionCreateView):
    pass


class TeacherRecorrigerQCMView(_DevoirQCMSeulement, TeacherRecorrigerView):
    pass


class _QuestionQCMSeulement:
    def get_queryset(self):
        return super().get_queryset().filter(devoir__modalite=Devoir.Modalite.QCM)


class TeacherQuestionDetailQCMView(_QuestionQCMSeulement, TeacherQuestionDetailView):
    pass


class TeacherQuestionUpdateQCMView(_QuestionQCMSeulement, TeacherQuestionUpdateView):
    pass


class TeacherQuestionDeleteQCMView(_QuestionQCMSeulement, TeacherQuestionDeleteView):
    pass


class TeacherChoixCreateQCMView(TeacherChoixCreateView):
    """Ajoute une proposition uniquement à une question de QCM du professeur."""

    def post(self, request, pk):
        professeur = _get_professeur(request)
        question = get_object_or_404(
            Question.objects.filter(
                devoir__cours_session__enseignant=professeur,
                devoir__modalite=Devoir.Modalite.QCM,
            )
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


class TeacherChoixDeleteQCMView(TeacherChoixDeleteView):
    """Retire une proposition uniquement d'une question QCM du professeur."""

    def post(self, request, pk):
        professeur = _get_professeur(request)
        choix = get_object_or_404(
            Choix.objects.filter(
                question__devoir__cours_session__enseignant=professeur,
                question__devoir__modalite=Devoir.Modalite.QCM,
            )
            if professeur
            else Choix.objects.none(),
            pk=pk,
        )
        question_pk = choix.question_id
        choix.delete()
        messages.success(request, "Proposition retirée.")
        return redirect("lms:question_detail", pk=question_pk)


class TeacherDevoirActionQCMView(TeacherDevoirActionView):
    """Publie un QCM uniquement lorsque son barème est exploitable."""

    def post(self, request, *args, **kwargs):
        devoir = self.get_object()
        action = request.POST.get("action")
        try:
            if action == "publier":
                if devoir.modalite == Devoir.Modalite.QCM:
                    probleme = services.motif_qcm_incomplet(devoir)
                    if probleme:
                        raise ValidationError(f"Questionnaire incomplet : {probleme}")
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
