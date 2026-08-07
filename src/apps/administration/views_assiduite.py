from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import ListView

from apps.academics.models import CoursDeSession, InscriptionSession, SessionAcademique
from apps.academics.models_assiduite import Presence, SeanceCours
from apps.academics.services_assiduite import enregistrer_presence
from apps.accounts.models import User

from .forms_assiduite import SeanceCoursForm


class AssiduiteAccessMixin(LoginRequiredMixin, UserPassesTestMixin):
    raise_exception = True

    def test_func(self):
        user = self.request.user
        return user.is_admin or user.is_secretariat or user.is_enseignant

    def cours_accessibles(self):
        queryset = CoursDeSession.objects.select_related(
            "cours",
            "session",
            "enseignant",
            "enseignant__user",
        )
        if self.request.user.role == User.Role.ENSEIGNANT and not self.request.user.is_superuser:
            queryset = queryset.filter(enseignant__user=self.request.user)
        return queryset


class AssiduiteListView(AssiduiteAccessMixin, ListView):
    """Vue globale réservée à la direction et au secrétariat.

    L'enseignant conserve l'accès aux feuilles de ses propres cours,
    mais ne peut pas parcourir l'assiduité de tout l'institut.
    """

    def test_func(self):
        user = self.request.user
        return user.is_admin or user.is_secretariat

    template_name = "administration/assiduite/liste.html"
    context_object_name = "offres"
    paginate_by = 20

    def get_queryset(self):
        queryset = self.cours_accessibles().annotate(
            nombre_inscrits=Count("inscriptions", distinct=True),
            nombre_seances=Count("seances_assiduite", distinct=True),
        )
        session = self.request.GET.get("session", "")
        recherche = self.request.GET.get("q", "").strip()
        if session:
            queryset = queryset.filter(session_id=session)
        if recherche:
            queryset = queryset.filter(
                Q(cours__titre__icontains=recherche)
                | Q(enseignant__nom__icontains=recherche)
                | Q(enseignant__prenom__icontains=recherche)
            )
        return queryset.order_by("-session__date_debut", "cours__titre")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "sessions": SessionAcademique.objects.order_by("-date_debut"),
                "current_session": self.request.GET.get("session", ""),
                "query": self.request.GET.get("q", ""),
            }
        )
        return context


class CoursAssiduiteView(AssiduiteAccessMixin, View):
    template_name = "administration/assiduite/cours.html"

    def get_cours(self):
        return get_object_or_404(self.cours_accessibles(), pk=self.kwargs["pk"])

    def get(self, request, *args, **kwargs):
        return self.render_page(SeanceCoursForm(cours_session=self.get_cours()))

    def post(self, request, *args, **kwargs):
        cours = self.get_cours()
        form = SeanceCoursForm(request.POST, cours_session=cours)
        if form.is_valid():
            seance = form.save(commit=False)
            seance.cours_session = cours
            seance.cree_par = request.user
            seance.save()
            messages.success(request, "La séance a été créée. La feuille de présence est prête.")
            return redirect("administration:assiduite_feuille", pk=seance.pk)
        return self.render_page(form)

    def render_page(self, form):
        from django.shortcuts import render

        cours = self.get_cours()
        seances = cours.seances_assiduite.annotate(
            nombre_saisies=Count("presences"),
            nombre_absences=Count(
                "presences",
                filter=Q(presences__statut__in=[Presence.Statut.ABSENT, Presence.Statut.EXCUSE]),
            ),
            nombre_retards=Count(
                "presences",
                filter=Q(presences__statut=Presence.Statut.RETARD),
            ),
        )
        return render(
            self.request,
            self.template_name,
            {
                "cours_session": cours,
                "seances": seances,
                "form": form,
                "nombre_inscrits": cours.inscriptions.count(),
            },
        )


class FeuilleAssiduiteView(AssiduiteAccessMixin, View):
    template_name = "administration/assiduite/feuille.html"

    def get_seance(self):
        return get_object_or_404(
            SeanceCours.objects.select_related(
                "cours_session__cours",
                "cours_session__session",
                "cours_session__enseignant",
                "cours_session__enseignant__user",
            ).filter(cours_session__in=self.cours_accessibles()),
            pk=self.kwargs["pk"],
        )

    @staticmethod
    def inscriptions(seance):
        return (
            InscriptionSession.objects.filter(cours_session=seance.cours_session)
            .select_related(
                "etudiant",
                "etudiant__utilisateur",
                "etudiant__parcours",
            )
            .order_by(
                "etudiant__utilisateur__last_name",
                "etudiant__utilisateur__first_name",
            )
        )

    def get(self, request, *args, **kwargs):
        return self.render_page()

    def post(self, request, *args, **kwargs):
        seance = self.get_seance()
        action = request.POST.get("action", "enregistrer")

        if action == "cloturer":
            seance.cloturee = True
            seance.save(update_fields=["cloturee", "updated_at"])
            messages.success(request, "La feuille de présence est clôturée.")
            return redirect("administration:assiduite_feuille", pk=seance.pk)

        if action == "rouvrir":
            seance.cloturee = False
            seance.save(update_fields=["cloturee", "updated_at"])
            messages.success(request, "La feuille de présence est de nouveau modifiable.")
            return redirect("administration:assiduite_feuille", pk=seance.pk)

        if seance.cloturee:
            messages.error(request, "Cette feuille est clôturée. Rouvrez-la avant toute correction.")
            return redirect("administration:assiduite_feuille", pk=seance.pk)

        inscriptions = list(self.inscriptions(seance))
        with transaction.atomic():
            for inscription in inscriptions:
                etudiant = inscription.etudiant
                enregistrer_presence(
                    seance=seance,
                    etudiant=etudiant,
                    statut=request.POST.get(
                        f"statut_{etudiant.pk}",
                        Presence.Statut.PRESENT,
                    ),
                    commentaire=request.POST.get(f"commentaire_{etudiant.pk}", ""),
                    auteur=request.user,
                )
        messages.success(request, f"Présences enregistrées pour {len(inscriptions)} étudiant(s).")
        return redirect("administration:assiduite_feuille", pk=seance.pk)

    def render_page(self):
        from django.shortcuts import render

        seance = self.get_seance()
        inscriptions = list(self.inscriptions(seance))
        presences = {
            presence.etudiant_id: presence
            for presence in Presence.objects.filter(seance=seance).select_related("etudiant")
        }
        rows = []
        for inscription in inscriptions:
            presence = presences.get(inscription.etudiant_id)
            rows.append(
                {
                    "etudiant": inscription.etudiant,
                    "statut": presence.statut if presence else Presence.Statut.PRESENT,
                    "commentaire": presence.commentaire if presence else "",
                    "presence": presence,
                }
            )
        compteurs = {
            statut: Presence.objects.filter(seance=seance, statut=statut).count()
            for statut, _ in Presence.Statut.choices
        }
        return render(
            self.request,
            self.template_name,
            {
                "seance": seance,
                "rows": rows,
                "statuts": Presence.Statut.choices,
                "compteurs": compteurs,
                "total_saisies": len(presences),
            },
        )
