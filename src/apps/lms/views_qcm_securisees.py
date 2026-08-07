"""Garde-fous des questionnaires dans le portail enseignant.

Le domaine QCM existe déjà dans ``lms`` : questions pondérées, propositions,
réponses conservées et note calculée automatiquement. Ce module ferme les
contournements restants sans dupliquer ces modèles.
"""

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Prefetch
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render

from apps.lms import services
from apps.lms.forms import ChoixForm, QuestionForm
from apps.lms.models import Choix, Devoir, Evaluation, Question
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

NOMBRE_PROPOSITIONS_DEFAUT = 4


def _propositions_depuis_requete(request=None) -> list[dict]:
    """Prépare les lignes du formulaire et conserve la saisie après une erreur."""
    if request is None:
        libelles = [""] * NOMBRE_PROPOSITIONS_DEFAUT
        correctes = set()
    else:
        libelles = request.POST.getlist("proposition")
        correctes = set(request.POST.getlist("correcte"))
        if not libelles:
            libelles = [""] * NOMBRE_PROPOSITIONS_DEFAUT

    lignes = [
        {
            "index": index,
            "libelle": libelle,
            "correcte": str(index) in correctes,
        }
        for index, libelle in enumerate(libelles)
    ]
    while len(lignes) < NOMBRE_PROPOSITIONS_DEFAUT:
        lignes.append({"index": len(lignes), "libelle": "", "correcte": False})
    return lignes


def _contexte_questionnaire(devoir, *, form_question, propositions) -> dict:
    """Reconstruit l'atelier sans perdre la saisie lorsqu'une création échoue."""
    questions = list(
        devoir.questions.prefetch_related(Prefetch("choix", queryset=Choix.objects.order_by("ordre", "id")))
    )
    return {
        "devoir": devoir,
        "questions": questions,
        "total_points": sum(question.points for question in questions),
        "motif_incomplet": services.motif_qcm_incomplet(devoir),
        "form_question": form_question,
        "propositions": propositions,
        "copies_rendues": devoir.copies.exclude(statut=Evaluation.StatutEvaluation.EN_ATTENTE).count(),
    }


class _DevoirQCMSeulement:
    """Refuse l'atelier QCM pour une autre modalité de devoir."""

    def devoir_ou_404(self, pk):
        devoir = super().devoir_ou_404(pk)
        if devoir.modalite != Devoir.Modalite.QCM:
            raise Http404("Ce devoir n'est pas un questionnaire.")
        return devoir


class TeacherQuestionnaireQCMView(_DevoirQCMSeulement, TeacherQuestionnaireView):
    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        contexte["propositions"] = _propositions_depuis_requete()
        return contexte


class TeacherQuestionCreateQCMView(_DevoirQCMSeulement, TeacherQuestionCreateView):
    """Crée la question et toutes ses propositions depuis un formulaire unique."""

    template_name = "lms/questionnaire.html"

    def post(self, request, pk):
        devoir = self.devoir_ou_404(pk)
        form = QuestionForm(request.POST)
        propositions = _propositions_depuis_requete(request)
        formulaire_valide = form.is_valid()

        non_vides = [ligne for ligne in propositions if ligne["libelle"].strip()]
        correctes = [ligne for ligne in propositions if ligne["correcte"] and ligne["libelle"].strip()]
        correction_sans_libelle = any(ligne["correcte"] and not ligne["libelle"].strip() for ligne in propositions)

        if len(non_vides) < 2:
            form.add_error(None, "Ajoutez au moins deux propositions de réponse.")
        if correction_sans_libelle:
            form.add_error(None, "Une proposition marquée correcte doit avoir un libellé.")
        if not correctes:
            form.add_error(None, "Indiquez au moins une bonne réponse.")
        if (
            formulaire_valide
            and form.cleaned_data["type_question"] == Question.TypeQuestion.CHOIX_UNIQUE
            and len(correctes) > 1
        ):
            form.add_error(None, "Une question à réponse unique ne peut avoir qu’une seule bonne réponse.")

        if formulaire_valide and not form.errors:
            with transaction.atomic():
                question = form.save(commit=False)
                question.devoir = devoir
                question.ordre = devoir.questions.count() + 1
                question.save()
                Choix.objects.bulk_create(
                    [
                        Choix(
                            question=question,
                            libelle=ligne["libelle"].strip(),
                            correct=ligne["correcte"],
                            ordre=ordre,
                        )
                        for ordre, ligne in enumerate(non_vides, start=1)
                    ]
                )
            messages.success(request, "Question et propositions ajoutées.")
            return redirect("lms:questionnaire", pk=devoir.pk)

        return render(
            request,
            self.template_name,
            _contexte_questionnaire(
                devoir,
                form_question=form,
                propositions=propositions,
            ),
            status=400,
        )


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
                messages.success(
                    request,
                    f"« {devoir.titre} » est ouvert : les étudiants en sont avertis.",
                )
            elif action == "clore":
                services.clore_devoir(devoir, par=request.user)
                messages.success(request, f"« {devoir.titre} » est clos.")
            else:
                messages.error(request, "Action inconnue.")
        except ValidationError as erreur:
            messages.error(request, erreur.messages[0])
        return redirect("lms:devoir_detail", pk=devoir.pk)
