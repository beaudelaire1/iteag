from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views import View
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from apps.core.mixins import AdminRoleRequiredMixin, StaffRoleRequiredMixin
from apps.formations.models import Discipline
from apps.library.formulaires import EmpruntForm, NoticeForm

from . import services
from .models import Emprunt, NoticeBibliographique


class CatalogueView(ListView):
    """Catalogue public de la bibliothèque — BIB-001/BIB-002."""

    model = NoticeBibliographique
    template_name = "library/catalogue.html"
    context_object_name = "notices"
    paginate_by = 20

    def get_template_names(self):
        if self.request.headers.get("HX-Request"):
            return ["library/partials/results.html"]
        return [self.template_name]

    def get_queryset(self):
        qs = super().get_queryset().select_related("discipline")
        q = self.request.GET.get("q", "").strip()
        discipline = self.request.GET.get("discipline", "").strip()
        author = self.request.GET.get("author", "").strip()
        year = self.request.GET.get("year", "").strip()
        ordering = self.request.GET.get("sort", "titre")

        if q:
            qs = self._apply_search(qs, q)
        if discipline:
            qs = qs.filter(discipline__slug=discipline)
        if author:
            qs = qs.filter(auteur__icontains=author)
        if year:
            qs = qs.filter(date_publication__icontains=year)

        if ordering == "auteur":
            qs = qs.order_by("auteur", "titre")
        elif ordering == "recent":
            qs = qs.order_by("-date_publication", "titre")
        elif ordering == "pertinence" and q:
            pass  # Déjà trié par rank dans _apply_search

        return qs

    def _apply_search(self, qs, q):
        """Full-text PostgreSQL, doublé d'un « contient » qui ne dépend pas de l'index.

        Le vecteur n'est calculé qu'au `save()` : une notice importée en masse
        reste invisible au plein texte seul. Et une cote comme « TP-222 » ne
        survit pas toujours à l'analyse lexicale. Les deux voies sont donc
        réunies plutôt qu'opposées.
        """
        from django.db import connection

        litteral = Q(titre__icontains=q) | Q(auteur__icontains=q) | Q(cote__icontains=q) | Q(isbn__icontains=q)

        if connection.vendor == "postgresql":
            from django.contrib.postgres.search import SearchQuery, SearchRank

            search_query = SearchQuery(q, config="french")
            qs = (
                qs.filter(Q(search_vector=search_query) | litteral)
                .annotate(rank=SearchRank("search_vector", search_query))
                .order_by("-rank", "titre")
            )
        else:
            qs = qs.filter(litteral | Q(mots_cles__icontains=q))
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["query"] = self.request.GET.get("q", "")
        context["current_discipline"] = self.request.GET.get("discipline", "")
        context["current_author"] = self.request.GET.get("author", "")
        context["current_year"] = self.request.GET.get("year", "")
        context["current_sort"] = self.request.GET.get("sort", "titre")
        context["disciplines"] = Discipline.objects.filter(notices__isnull=False).distinct().order_by("nom")

        if self.request.user.is_authenticated:
            user_emprunts = Emprunt.objects.filter(
                emprunteur=self.request.user,
                statut__in=[Emprunt.Statut.RESERVE, Emprunt.Statut.EN_COURS, Emprunt.Statut.EN_RETARD],
            )
            context["user_reservations_notice_ids"] = set(
                e.notice_id for e in user_emprunts if e.statut == Emprunt.Statut.RESERVE
            )
            context["user_active_loans_notice_ids"] = set(
                e.notice_id for e in user_emprunts if e.statut in (Emprunt.Statut.EN_COURS, Emprunt.Statut.EN_RETARD)
            )
        else:
            context["user_reservations_notice_ids"] = set()
            context["user_active_loans_notice_ids"] = set()

        return context


class NoticeDetailView(DetailView):
    model = NoticeBibliographique
    template_name = "library/notice_detail.html"
    context_object_name = "notice"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.user.is_authenticated:
            context["user_emprunt"] = Emprunt.objects.filter(
                notice=self.object,
                emprunteur=self.request.user,
                statut__in=[Emprunt.Statut.RESERVE, Emprunt.Statut.EN_COURS, Emprunt.Statut.EN_RETARD],
            ).first()
        return context


# ══════════════════════════════════════════════
# Back-office — gestion des notices
# ══════════════════════════════════════════════
#
# La bibliothèque n'avait aucun écran de gestion : le catalogue se consultait
# mais ne s'administrait que par l'interface Django. Or tenir le fonds fait
# partie du travail courant du secrétariat, au même titre que la boutique.


class GestionNoticesView(StaffRoleRequiredMixin, ListView):
    """Fonds documentaire, avec recherche et état de disponibilité."""

    model = NoticeBibliographique
    template_name = "library/gestion.html"
    context_object_name = "notices"
    paginate_by = 25

    def get_queryset(self):
        queryset = NoticeBibliographique.objects.select_related("discipline").order_by("cote", "titre")
        recherche = self.request.GET.get("q", "").strip()
        discipline = self.request.GET.get("discipline", "").strip()
        disponibilite = self.request.GET.get("disponible", "").strip()

        if recherche:
            queryset = queryset.filter(
                Q(titre__icontains=recherche)
                | Q(auteur__icontains=recherche)
                | Q(cote__icontains=recherche)
                | Q(isbn__icontains=recherche)
            )
        if discipline:
            queryset = queryset.filter(discipline_id=discipline)
        if disponibilite in ("oui", "non"):
            queryset = queryset.filter(disponible=disponibilite == "oui")
        return queryset

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        fonds = NoticeBibliographique.objects.all()
        contexte.update(
            {
                "disciplines": Discipline.objects.order_by("ordre", "nom"),
                "query": self.request.GET.get("q", ""),
                "current_discipline": self.request.GET.get("discipline", ""),
                "current_disponible": self.request.GET.get("disponible", ""),
                "total_fonds": fonds.count(),
                "total_sorties": fonds.filter(disponible=False).count(),
                "total_sans_cote": fonds.filter(cote="").count(),
            }
        )
        return contexte


class NoticeCreateView(StaffRoleRequiredMixin, CreateView):
    model = NoticeBibliographique
    form_class = NoticeForm
    template_name = "administration/form.html"

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        contexte.update(
            {
                "form_title": "Nouvelle notice",
                "nav": "bibliotheque",
                "cancel_url": reverse("library:gestion"),
            }
        )
        return contexte

    def form_valid(self, form):
        messages.success(self.request, f"Notice « {form.instance.titre} » ajoutée au fonds.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("library:gestion")


class NoticeUpdateView(StaffRoleRequiredMixin, UpdateView):
    model = NoticeBibliographique
    form_class = NoticeForm
    template_name = "administration/form.html"

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        contexte.update(
            {
                "form_title": f"Modifier « {self.object.titre} »",
                "nav": "bibliotheque",
                "cancel_url": reverse("library:gestion"),
            }
        )
        return contexte

    def form_valid(self, form):
        messages.success(self.request, "Notice mise à jour.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("library:gestion")


class NoticeDisponibiliteView(StaffRoleRequiredMixin, View):
    """Bascule « en rayon / sorti » en un clic.

    Le geste le plus fréquent du fonds mérite de ne pas passer par un
    formulaire complet : c'est un prêt ou un retour, pas une correction de
    notice.
    """

    http_method_names = ["post"]

    def post(self, request, pk):
        notice = get_object_or_404(NoticeBibliographique, pk=pk)
        notice.disponible = not notice.disponible
        notice.save(update_fields=["disponible", "updated_at"])
        etat = "de retour en rayon" if notice.disponible else "sortie du fonds"
        messages.success(request, f"« {notice.titre} » {etat}.")
        return redirect(request.META.get("HTTP_REFERER") or reverse("library:gestion"))


class NoticeDeleteView(AdminRoleRequiredMixin, DeleteView):
    """Retrait définitif — réservé à la direction, comme toute suppression."""

    model = NoticeBibliographique
    template_name = "administration/confirm_delete.html"

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        contexte.update(
            {
                "objet": self.object,
                "titre": "Retirer cette notice du fonds",
                "cancel_url": reverse("library:gestion"),
                "nav": "bibliotheque",
            }
        )
        return contexte

    def get_success_url(self):
        messages.success(self.request, "Notice retirée du fonds.")
        return reverse("library:gestion")


class ReserverOuvrageView(LoginRequiredMixin, View):
    """Permet à un utilisateur connecté de réserver un ouvrage disponible."""

    http_method_names = ["post"]

    def post(self, request, pk):
        notice = get_object_or_404(NoticeBibliographique, pk=pk)
        try:
            emprunt = services.reserver_ouvrage(notice, request.user)
        except ValidationError as erreur:
            messages.error(request, erreur.messages[0])
        else:
            dt_fmt = emprunt.date_retour_prevue.strftime("%d/%m/%Y")
            messages.success(
                request,
                (
                    f"« {notice.titre} » a été réservé. "
                    f"Présentez-vous au secrétariat pour le retrait (retour prévu le {dt_fmt})."
                ),
            )
        return redirect("library:notice_detail", pk=notice.pk)


class AnnulerReservationView(LoginRequiredMixin, View):
    """Permet à un utilisateur (étudiant ou enseignant) d'annuler sa réservation d'ouvrage."""

    http_method_names = ["post"]

    def post(self, request, pk):
        emprunt = Emprunt.objects.filter(pk=pk, emprunteur=request.user, statut=Emprunt.Statut.RESERVE).first()
        if not emprunt:
            emprunt = get_object_or_404(
                Emprunt, notice_id=pk, emprunteur=request.user, statut=Emprunt.Statut.RESERVE
            )

        try:
            notice = services.annuler_reservation(emprunt, request.user)
        except ValidationError as erreur:
            messages.error(request, erreur.messages[0])
        else:
            messages.success(request, f"Votre réservation pour « {notice.titre} » a été annulée.")

        referer = request.META.get("HTTP_REFERER")
        if referer:
            return redirect(referer)
        return redirect("library:catalogue")


class GestionEmpruntsView(StaffRoleRequiredMixin, ListView):
    """Tableau de bord de gestion des emprunts pour le secrétariat."""

    model = Emprunt
    template_name = "library/gestion_emprunts.html"
    context_object_name = "emprunts"
    paginate_by = 30

    def get_queryset(self):
        qs = Emprunt.objects.select_related("notice", "emprunteur")
        statut = self.request.GET.get("statut", "").strip()
        if statut:
            qs = qs.filter(statut=statut)
        return qs

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        contexte.update(
            {
                "statuts": Emprunt.Statut.choices,
                "statut_courant": self.request.GET.get("statut", ""),
                "nb_en_cours": Emprunt.objects.filter(statut=Emprunt.Statut.EN_COURS).count(),
                "nb_retards": Emprunt.objects.filter(statut=Emprunt.Statut.EN_RETARD).count(),
                "nb_reservations": Emprunt.objects.filter(statut=Emprunt.Statut.RESERVE).count(),
                "nb_rendus": Emprunt.objects.filter(statut=Emprunt.Statut.RENDU).count(),
            }
        )
        return contexte


class EmpruntActionView(StaffRoleRequiredMixin, View):
    """Actions de secrétariat : valider le retrait ou enregistrer la restitution."""

    http_method_names = ["post"]

    def post(self, request, pk):
        emprunt = get_object_or_404(Emprunt, pk=pk)
        action = request.POST.get("action", "").strip()
        try:
            if action == "valider_retrait":
                services.valider_retrait(emprunt)
                messages.success(request, f"Retrait validé pour « {emprunt.notice.titre} ».")
            elif action == "restituer":
                commentaire = request.POST.get("commentaire", "")
                services.restituer_ouvrage(emprunt, commentaire=commentaire)
                messages.success(request, f"Ouvrage « {emprunt.notice.titre} » restitué et remis en rayon.")
            else:
                raise ValidationError("Action invalide.")
        except ValidationError as erreur:
            messages.error(request, erreur.messages[0])
        return redirect("library:gestion_emprunts")


class EmpruntCreateView(StaffRoleRequiredMixin, CreateView):
    """Création manuelle d'un emprunt ou réservation par le secrétariat."""

    model = Emprunt
    form_class = EmpruntForm
    template_name = "library/emprunt_form.html"

    def form_valid(self, form):
        emprunt = form.save(commit=False)
        notice = emprunt.notice
        notice.disponible = False
        notice.save(update_fields=["disponible", "updated_at"])
        emprunt.save()
        messages.success(
            self.request,
            f"L'emprunt pour « {notice.titre} » a été créé avec succès.",
        )
        dt_fmt = emprunt.date_retour_prevue.strftime("%d/%m/%Y")
        services.notifier(
            emprunt.emprunteur,
            f"Nouvel emprunt enregistré — {notice.titre}",
            message=f"L'emprunt de « {notice.titre} » a été enregistré par le secrétariat. Date d'échéance : {dt_fmt}.",
            envoyer_par_email=True,
        )
        return redirect("library:gestion_emprunts")


class EmpruntUpdateView(StaffRoleRequiredMixin, UpdateView):
    """Modification/prolongation d'un emprunt existant par le secrétariat."""

    model = Emprunt
    form_class = EmpruntForm
    template_name = "library/emprunt_form.html"

    def form_valid(self, form):
        emprunt = form.save()
        messages.success(
            self.request,
            f"L'emprunt de « {emprunt.notice.titre} » a été mis à jour avec succès.",
        )
        return redirect("library:gestion_emprunts")


class EmpruntDeleteView(StaffRoleRequiredMixin, DeleteView):
    """Suppression/annulation d'un emprunt par le secrétariat."""

    model = Emprunt
    template_name = "library/emprunt_confirm_delete.html"

    def form_valid(self, form):
        emprunt = self.get_object()
        notice = emprunt.notice
        if emprunt.statut != Emprunt.Statut.RENDU:
            notice.disponible = True
            notice.save(update_fields=["disponible", "updated_at"])
        messages.success(self.request, f"L'emprunt pour « {notice.titre} » a été supprimé.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("library:gestion_emprunts")


class MesEmpruntsView(LoginRequiredMixin, ListView):
    """Espace personnel de l'emprunteur (étudiant ou enseignant).
    
    Affiche la liste des livres actuellement en sa possession (prêts en cours et en retard),
    les réservations en attente de retrait (avec possibilité d'annuler), ainsi que l'historique.
    """

    model = Emprunt
    template_name = "library/mes_emprunts.html"
    context_object_name = "emprunts"

    def get_queryset(self):
        return (
            Emprunt.objects.filter(emprunteur=self.request.user)
            .select_related("notice", "notice__discipline")
            .order_by("-created_at")
        )

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        tous = list(self.get_queryset())
        contexte["emprunts_en_cours"] = [
            e for e in tous if e.statut in (Emprunt.Statut.EN_COURS, Emprunt.Statut.EN_RETARD)
        ]
        contexte["reservations"] = [
            e for e in tous if e.statut == Emprunt.Statut.RESERVE
        ]
        contexte["historique"] = [
            e for e in tous if e.statut == Emprunt.Statut.RENDU
        ]
        return contexte

