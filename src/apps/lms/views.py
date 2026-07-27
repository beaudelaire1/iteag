from django.contrib import messages
from django.db.models import Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DeleteView, DetailView, ListView, TemplateView, UpdateView

from apps.academics.models import CoursDeSession
from apps.core.mixins import TeacherRoleRequiredMixin

from .forms import AnnonceForm, GradeForm, ParametresEvaluationForm, RessourceUploadForm
from .models import Annonce, Evaluation, RessourcePedagogique

# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────


def _get_professeur(request):
    return getattr(request.user, "profil_professeur", None)


def _teacher_courses(request):
    prof = _get_professeur(request)
    if prof is None:
        return CoursDeSession.objects.none()
    return CoursDeSession.objects.filter(enseignant=prof).select_related("cours", "session")


# ──────────────────────────────────────────────
# Dashboard
# ──────────────────────────────────────────────


class TeacherDashboardView(TeacherRoleRequiredMixin, TemplateView):
    template_name = "lms/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        professeur = _get_professeur(self.request)
        cours_assignes = CoursDeSession.objects.none()
        pending_evaluations = Evaluation.objects.none()
        recent_annonces = Annonce.objects.none()

        if professeur is not None:
            cours_assignes = CoursDeSession.objects.filter(enseignant=professeur).select_related("cours", "session")
            pending_evaluations = Evaluation.objects.filter(
                cours_session__enseignant=professeur,
                statut__in=[Evaluation.StatutEvaluation.SOUMIS, Evaluation.StatutEvaluation.EN_CORRECTION],
            ).select_related("etudiant__utilisateur", "cours_session__cours", "cours_session__session")[:8]
            recent_annonces = Annonce.objects.filter(cours_session__enseignant=professeur).select_related(
                "cours_session__cours"
            )[:5]

        context.update(
            {
                "professeur": professeur,
                "cours_assignes": cours_assignes,
                "pending_evaluations": pending_evaluations,
                "recent_annonces": recent_annonces,
            }
        )
        return context


# ──────────────────────────────────────────────
# Course detail
# ──────────────────────────────────────────────


class TeacherCourseDetailView(TeacherRoleRequiredMixin, DetailView):
    model = CoursDeSession
    template_name = "lms/course_detail.html"
    context_object_name = "cours_session"

    def get_queryset(self):
        professeur = _get_professeur(self.request)
        queryset = CoursDeSession.objects.select_related("cours", "session", "enseignant")
        if professeur is None:
            return queryset.none()
        return queryset.filter(enseignant=professeur)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        cours_session = self.object
        context.update(
            {
                "inscriptions": cours_session.inscriptions.select_related(
                    "etudiant__utilisateur", "etudiant__parcours"
                ),
                "ressources": cours_session.ressources.all(),
                "annonces": cours_session.annonces.all(),
                "evaluations": cours_session.evaluations.select_related("etudiant__utilisateur").all(),
            }
        )
        return context


# ──────────────────────────────────────────────
# Courses list
# ──────────────────────────────────────────────


class TeacherCoursesListView(TeacherRoleRequiredMixin, ListView):
    template_name = "lms/courses_list.html"
    context_object_name = "cours_list"

    def get_queryset(self):
        return _teacher_courses(self.request).prefetch_related("inscriptions")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["professeur"] = _get_professeur(self.request)
        return context


# ──────────────────────────────────────────────
# Evaluations list (all pending across courses)
# ──────────────────────────────────────────────


class TeacherEvaluationsListView(TeacherRoleRequiredMixin, ListView):
    """
    La liste croît en étudiants × cours × évaluations : c'est celle qui grossit
    le plus vite de tout l'espace enseignant. Sans pagination ni filtre, elle
    finissait par être la page la plus lourde du portail, et les copies à
    corriger s'y noyaient.
    """

    template_name = "lms/evaluations_list.html"
    context_object_name = "evaluations"
    paginate_by = 30

    def get_queryset(self):
        prof = _get_professeur(self.request)
        if prof is None:
            return Evaluation.objects.none()
        requete = (
            Evaluation.objects.filter(cours_session__enseignant=prof)
            .select_related("etudiant__utilisateur", "cours_session__cours", "cours_session__session")
            .order_by("statut", "-created_at")
        )
        recherche = self.request.GET.get("q", "").strip()
        statut = self.request.GET.get("statut", "")
        cours = self.request.GET.get("cours", "")
        if recherche:
            requete = requete.filter(
                Q(etudiant__utilisateur__last_name__icontains=recherche)
                | Q(etudiant__utilisateur__first_name__icontains=recherche)
                | Q(etudiant__numero_etudiant__icontains=recherche)
                | Q(cours_session__cours__titre__icontains=recherche)
            )
        if statut:
            requete = requete.filter(statut=statut)
        if cours:
            requete = requete.filter(cours_session_id=cours)
        return requete

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        prof = _get_professeur(self.request)
        context.update(
            {
                "professeur": prof,
                "statut_choices": Evaluation.StatutEvaluation.choices,
                "current_statut": self.request.GET.get("statut", ""),
                "current_cours": self.request.GET.get("cours", ""),
                "query": self.request.GET.get("q", ""),
                "cours_enseignes": (
                    CoursDeSession.objects.filter(enseignant=prof).select_related("cours", "session")
                    if prof
                    else CoursDeSession.objects.none()
                ),
                "a_corriger": Evaluation.objects.filter(
                    cours_session__enseignant=prof,
                    statut__in=[Evaluation.StatutEvaluation.SOUMIS, Evaluation.StatutEvaluation.EN_CORRECTION],
                ).count()
                if prof
                else 0,
            }
        )
        return context


# ──────────────────────────────────────────────
# Announcements list
# ──────────────────────────────────────────────


class TeacherAnnoncesListView(TeacherRoleRequiredMixin, ListView):
    template_name = "lms/annonces_list.html"
    context_object_name = "annonces"

    def get_queryset(self):
        prof = _get_professeur(self.request)
        if prof is None:
            return Annonce.objects.none()
        return Annonce.objects.filter(cours_session__enseignant=prof).select_related("cours_session__cours")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["professeur"] = _get_professeur(self.request)
        return context


# ──────────────────────────────────────────────
# Resource upload
# ──────────────────────────────────────────────


class TeacherResourceUploadView(TeacherRoleRequiredMixin, CreateView):
    model = None  # set via form
    form_class = RessourceUploadForm
    template_name = "lms/resource_form.html"

    def dispatch(self, request, *args, **kwargs):
        self.cours_session = get_object_or_404(_teacher_courses(request), pk=kwargs["cours_pk"])
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["cours_session"] = self.cours_session
        return context

    def form_valid(self, form):
        ressource = form.save(commit=False)
        ressource.cours_session = self.cours_session
        ressource.uploade_par = self.request.user
        ressource.save()
        messages.success(self.request, "Ressource ajoutée avec succès.")
        return redirect(reverse("lms:course_detail", kwargs={"pk": self.cours_session.pk}))


class TeacherResourceUpdateView(TeacherRoleRequiredMixin, UpdateView):
    model = RessourcePedagogique
    form_class = RessourceUploadForm
    template_name = "lms/resource_form.html"
    context_object_name = "ressource"

    def get_queryset(self):
        prof = _get_professeur(self.request)
        if prof is None:
            return RessourcePedagogique.objects.none()
        return RessourcePedagogique.objects.filter(cours_session__enseignant=prof).select_related(
            "cours_session__cours"
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["cours_session"] = self.object.cours_session
        return context

    def form_valid(self, form):
        self.object = form.save()
        messages.success(self.request, "Ressource mise à jour.")
        return redirect("lms:course_detail", pk=self.object.cours_session_id)


class TeacherResourceDeleteView(TeacherRoleRequiredMixin, DeleteView):
    model = RessourcePedagogique
    template_name = "lms/confirm_delete.html"
    context_object_name = "objet"

    def get_queryset(self):
        prof = _get_professeur(self.request)
        if prof is None:
            return RessourcePedagogique.objects.none()
        return RessourcePedagogique.objects.filter(cours_session__enseignant=prof)

    def form_valid(self, form):
        messages.success(self.request, "Ressource supprimée.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("lms:course_detail", kwargs={"pk": self.object.cours_session_id})


# ──────────────────────────────────────────────
# Grade evaluation
# ──────────────────────────────────────────────


class TeacherGradeEvaluationView(TeacherRoleRequiredMixin, UpdateView):
    model = Evaluation
    form_class = GradeForm
    template_name = "lms/grade_form.html"
    context_object_name = "evaluation"

    def get_queryset(self):
        """Toutes les copies de l'enseignant, y compris déjà notées.

        Le filtre se limitait à « soumis » et « en correction » : une note
        posée devenait définitive, et corriger une erreur de saisie demandait
        un passage par l'administration Django. Une note se corrige — c'est le
        cas d'usage le plus banal de la vie d'un enseignant.

        Ce qui est publié reste modifiable, mais l'écran le signale : l'étudiant
        a déjà vu la note, et la changer sans le lui dire serait pire que de ne
        pas pouvoir la changer.
        """
        prof = _get_professeur(self.request)
        if prof is None:
            return Evaluation.objects.none()
        return Evaluation.objects.filter(cours_session__enseignant=prof).select_related(
            "etudiant__utilisateur", "cours_session__cours", "cours_session__session"
        )

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        contexte["deja_publiee"] = self.object.statut == Evaluation.StatutEvaluation.PUBLIE
        return contexte

    def form_valid(self, form):
        evaluation = form.save(commit=False)
        etait_publiee = Evaluation.objects.get(pk=evaluation.pk).statut == Evaluation.StatutEvaluation.PUBLIE
        # Une note déjà publiée le reste : la repasser en « notée » la
        # retirerait du relevé de l'étudiant sans prévenir personne.
        evaluation.statut = Evaluation.StatutEvaluation.PUBLIE if etait_publiee else Evaluation.StatutEvaluation.NOTE
        evaluation.date_notation = timezone.now()
        evaluation.save()

        nom = evaluation.etudiant.utilisateur.get_full_name()
        if etait_publiee:
            messages.success(self.request, f"Note de {nom} corrigée. Elle est visible immédiatement par l'étudiant.")
        else:
            messages.success(self.request, f"Note enregistrée pour {nom}.")
        return redirect(reverse("lms:course_detail", kwargs={"pk": evaluation.cours_session.pk}))


# ──────────────────────────────────────────────
# Publish grades (batch action)
# ──────────────────────────────────────────────


class TeacherPublishGradesView(TeacherRoleRequiredMixin, DetailView):
    """POST-only: publish all 'noté' evaluations for a course session."""

    model = CoursDeSession
    http_method_names = ["post"]

    def get_queryset(self):
        prof = _get_professeur(self.request)
        if prof is None:
            return CoursDeSession.objects.none()
        return CoursDeSession.objects.filter(enseignant=prof)

    def post(self, request, *args, **kwargs):
        from apps.academics.services.credits import crediter_publication

        cours_session = self.get_object()
        updated = cours_session.evaluations.filter(statut=Evaluation.StatutEvaluation.NOTE).update(
            statut=Evaluation.StatutEvaluation.PUBLIE
        )
        # Publier une note, c'est arrêter un résultat : le crédit ECTS est
        # porté au dossier dans le même geste, sinon le relevé de l'étudiant
        # reste vierge quoi qu'il valide.
        credites = crediter_publication(cours_session)

        message = f"{updated} évaluation(s) publiée(s)."
        if credites:
            message += f" {credites} crédit(s) ECTS porté(s) au dossier."
        messages.success(request, message)
        return redirect(reverse("lms:course_detail", kwargs={"pk": cours_session.pk}))


class TeacherPrepareEvaluationsView(TeacherRoleRequiredMixin, DetailView):
    """Crée une évaluation à remettre pour chaque étudiant inscrit au cours."""

    model = CoursDeSession
    http_method_names = ["post"]

    def get_queryset(self):
        return _teacher_courses(self.request).prefetch_related("inscriptions__etudiant")

    def post(self, request, *args, **kwargs):
        cours_session = self.get_object()
        evaluation_type = request.POST.get("type_evaluation")
        valid_types = {value for value, _ in Evaluation.TypeEvaluation.choices}
        if evaluation_type not in valid_types:
            messages.error(request, "Choisissez un type d'évaluation valide.")
            return redirect("lms:course_detail", pk=cours_session.pk)

        created = 0
        for inscription in cours_session.inscriptions.all():
            _, was_created = Evaluation.objects.get_or_create(
                cours_session=cours_session,
                etudiant=inscription.etudiant,
                type_evaluation=evaluation_type,
                defaults={"statut": Evaluation.StatutEvaluation.EN_ATTENTE},
            )
            created += int(was_created)
        messages.success(request, f"{created} évaluation(s) préparée(s) pour les étudiants inscrits.")
        return redirect("lms:course_detail", pk=cours_session.pk)


# ──────────────────────────────────────────────
# Announcement create
# ──────────────────────────────────────────────


class TeacherAnnouncementCreateView(TeacherRoleRequiredMixin, CreateView):
    form_class = AnnonceForm
    template_name = "lms/announcement_form.html"

    def dispatch(self, request, *args, **kwargs):
        self.cours_session = get_object_or_404(_teacher_courses(request), pk=kwargs["cours_pk"])
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["cours_session"] = self.cours_session
        return context

    def form_valid(self, form):
        annonce = form.save(commit=False)
        annonce.cours_session = self.cours_session
        annonce.auteur = self.request.user
        annonce.save()
        messages.success(self.request, "Annonce publiée.")
        return redirect(reverse("lms:course_detail", kwargs={"pk": self.cours_session.pk}))


# ──────────────────────────────────────────────
# Announcement edit
# ──────────────────────────────────────────────


class TeacherAnnouncementUpdateView(TeacherRoleRequiredMixin, UpdateView):
    model = Annonce
    form_class = AnnonceForm
    template_name = "lms/announcement_form.html"
    context_object_name = "annonce"

    def get_queryset(self):
        prof = _get_professeur(self.request)
        if prof is None:
            return Annonce.objects.none()
        return Annonce.objects.filter(cours_session__enseignant=prof).select_related("cours_session__cours")

    def form_valid(self, form):
        form.save()
        messages.success(self.request, "Annonce modifiée.")
        return redirect(reverse("lms:annonces_list"))


class TeacherAnnouncementDeleteView(TeacherRoleRequiredMixin, DeleteView):
    model = Annonce
    template_name = "lms/confirm_delete.html"
    context_object_name = "objet"

    def get_queryset(self):
        prof = _get_professeur(self.request)
        if prof is None:
            return Annonce.objects.none()
        return Annonce.objects.filter(cours_session__enseignant=prof)

    def form_valid(self, form):
        messages.success(self.request, "Annonce supprimée.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("lms:annonces_list")


# ──────────────────────────────────────────────
# Paramètres d'évaluation d'un cours
# ──────────────────────────────────────────────


class TeacherParametresEvaluationView(TeacherRoleRequiredMixin, UpdateView):
    """Date d'examen et fenêtre de remise.

    L'enseignant n'avait aucun moyen de clore la remise autrement qu'en le
    demandant : un devoir pouvait arriver après la publication des notes des
    autres.
    """

    model = CoursDeSession
    form_class = ParametresEvaluationForm
    template_name = "lms/parametres_evaluation.html"
    context_object_name = "cours_session"

    def get_queryset(self):
        return _teacher_courses(self.request)

    def form_valid(self, form):
        messages.success(self.request, "Calendrier d'évaluation enregistré. Les étudiants le voient sur leur page.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("lms:course_detail", kwargs={"pk": self.object.pk})


class TeacherOuvrirDepotView(TeacherRoleRequiredMixin, View):
    """Ouvre ou ferme la remise sur-le-champ, sans passer par le calendrier.

    Le geste courant est « je ferme maintenant » ou « je rouvre pour un
    retardataire » : le faire en éditant deux dates serait disproportionné.
    """

    http_method_names = ["post"]

    def post(self, request, pk):
        cours_session = get_object_or_404(_teacher_courses(request), pk=pk)
        maintenant = timezone.now()

        if cours_session.depot_est_ouvert:
            cours_session.depot_fermeture = maintenant
            if cours_session.depot_ouverture and cours_session.depot_ouverture > maintenant:
                cours_session.depot_ouverture = maintenant
            message = "Remise close. Les étudiants ne peuvent plus déposer."
        else:
            cours_session.depot_ouverture = maintenant
            cours_session.depot_fermeture = None
            message = "Remise rouverte, sans échéance. Pensez à fixer une fermeture."

        cours_session.save(update_fields=["depot_ouverture", "depot_fermeture", "updated_at"])
        messages.success(request, message)
        return redirect(reverse("lms:course_detail", kwargs={"pk": cours_session.pk}))


# ──────────────────────────────────────────────
# Espace documents
# ──────────────────────────────────────────────


class TeacherDocumentsView(TeacherRoleRequiredMixin, ListView):
    """Toutes les copies de l'enseignant : remises, corrigées, en attente.

    Les copies n'étaient atteignables qu'une par une, depuis la page de
    notation de chacune. Les retrouver — pour en réimprimer une, vérifier qui
    n'a rien rendu, ou récupérer un corrigé — demandait de parcourir les cours.
    """

    template_name = "lms/documents.html"
    context_object_name = "evaluations"
    paginate_by = 30

    def get_queryset(self):
        prof = _get_professeur(self.request)
        if prof is None:
            return Evaluation.objects.none()

        requete = Evaluation.objects.filter(cours_session__enseignant=prof).select_related(
            "etudiant__utilisateur", "cours_session__cours", "cours_session__session"
        )
        cours = self.request.GET.get("cours", "")
        etat = self.request.GET.get("etat", "")

        if cours:
            requete = requete.filter(cours_session_id=cours)
        if etat == "a_corriger":
            requete = requete.filter(
                statut__in=[Evaluation.StatutEvaluation.SOUMIS, Evaluation.StatutEvaluation.EN_CORRECTION]
            )
        elif etat == "corrigees":
            requete = requete.exclude(fichier_corrige="")
        elif etat == "sans_remise":
            requete = requete.filter(fichier_soumis="")
        return requete.order_by("cours_session__cours__titre", "etudiant__numero_etudiant")

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        toutes = Evaluation.objects.filter(cours_session__enseignant=_get_professeur(self.request))
        contexte.update(
            {
                "mes_cours": _teacher_courses(self.request),
                "cours_courant": self.request.GET.get("cours", ""),
                "etat_courant": self.request.GET.get("etat", ""),
                "total_remises": toutes.exclude(fichier_soumis="").count(),
                "total_corriges": toutes.exclude(fichier_corrige="").count(),
                "total_sans_remise": toutes.filter(fichier_soumis="").count(),
            }
        )
        return contexte


class TeacherFichierEvaluationView(TeacherRoleRequiredMixin, View):
    """
    Sert une copie — remise ou corrigée — après vérification du droit.

    Les gabarits pointaient jusqu'ici sur l'adresse média directe. Un devoir
    d'étudiant y est un fichier public à qui connaît son chemin : le contrôle
    d'accès s'arrêtait à la page, pas au document. Ici, la requête n'aboutit
    que si la copie appartient à un cours de cet enseignant.
    """

    def get(self, request, pk, genre):
        prof = _get_professeur(request)
        evaluation = get_object_or_404(Evaluation, pk=pk, cours_session__enseignant=prof)

        fichier = evaluation.fichier_soumis if genre == "remise" else evaluation.fichier_corrige
        if not fichier:
            raise Http404
        return FileResponse(fichier.open("rb"), as_attachment=True, filename=fichier.name.split("/")[-1])
