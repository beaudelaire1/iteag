"""Articles de recherche — rédaction, relecture, lecture publique.

Trois publics dans un seul module, parce qu'ils portent sur le même objet et
que les séparer obligerait à répéter les mêmes gardes trois fois :

- l'**auteur** rédige et soumet ce qui lui appartient ;
- le **relecteur** (administration ou secrétariat) publie, renvoie ou retire ;
- le **visiteur** ne voit que ce qui est publié.
"""

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views import View
from django.views.generic import DetailView, ListView, TemplateView

from apps.core.mixins import StaffRoleRequiredMixin, TeacherRoleRequiredMixin
from apps.core.models import JournalAudit, Notification
from apps.core.services.audit import journaliser
from apps.core.services.notifications import notifier, notifier_plusieurs
from apps.website.formulaires_articles import ArticleForm, IllustrationForm
from apps.website.models_publications import Article, ImageArticle


def _fiche_enseignant(utilisateur):
    professeur = getattr(utilisateur, "profil_professeur", None)
    if professeur is None:
        raise Http404("Aucune fiche enseignant n'est rattachée à ce compte.")
    return professeur


# ══════════════════════════════════════════════
# L'auteur
# ══════════════════════════════════════════════


class MesArticlesView(TeacherRoleRequiredMixin, ListView):
    template_name = "website/articles/mes_articles.html"
    context_object_name = "articles"
    paginate_by = 20

    def get_queryset(self):
        return Article.objects.filter(auteur=_fiche_enseignant(self.request.user))

    def get_context_data(self, **kwargs):
        return {**super().get_context_data(**kwargs), "nav": "articles"}


class ArticleEditionView(TeacherRoleRequiredMixin, TemplateView):
    """Création et modification, sur le même écran.

    Un article publié n'est pas modifiable : il faut le retirer d'abord. Le
    changer en place transformerait sous les yeux du lecteur une page déjà
    indexée, sans qu'elle soit repassée par la relecture.
    """

    template_name = "website/articles/article_form.html"

    def _article(self):
        if "pk" not in self.kwargs:
            return None
        return get_object_or_404(
            Article.objects.prefetch_related("illustrations"),
            pk=self.kwargs["pk"],
            auteur=_fiche_enseignant(self.request.user),
        )

    def get_context_data(self, **kwargs):
        article = self._article()
        return {
            **super().get_context_data(**kwargs),
            "nav": "articles",
            "article": article,
            "form": kwargs.get("form") or ArticleForm(instance=article),
            "form_illustration": IllustrationForm(),
            "verrouille": article is not None and not article.est_modifiable,
        }

    def post(self, request, *args, **kwargs):
        article = self._article()
        if article is not None and not article.est_modifiable:
            messages.error(request, "Retirez l'article de la publication avant de le modifier.")
            return redirect("website:mes_articles")

        formulaire = ArticleForm(request.POST, request.FILES, instance=article)
        if not formulaire.is_valid():
            return self.render_to_response(self.get_context_data(form=formulaire))

        article = formulaire.save(commit=False)
        if article.auteur_id is None:
            article.auteur = _fiche_enseignant(request.user)
        article.save()

        messages.success(request, "Article enregistré. Il reste en brouillon tant que vous ne l'avez pas soumis.")
        return redirect("website:article_edition", pk=article.pk)


class IllustrationCreateView(TeacherRoleRequiredMixin, View):
    """Dépôt d'une figure, que l'auteur insère ensuite où il veut dans le texte."""

    http_method_names = ["post"]

    def post(self, request, pk):
        article = get_object_or_404(Article, pk=pk, auteur=_fiche_enseignant(request.user))
        formulaire = IllustrationForm(request.POST, request.FILES)
        if formulaire.is_valid():
            illustration = formulaire.save(commit=False)
            illustration.article = article
            illustration.save()
            messages.success(request, "Illustration déposée : insérez-la depuis la barre d'outils.")
        else:
            messages.error(request, "Choisissez une image valide.")
        return redirect("website:article_edition", pk=article.pk)


class IllustrationDeleteView(TeacherRoleRequiredMixin, View):
    http_method_names = ["post"]

    def post(self, request, pk):
        illustration = get_object_or_404(
            ImageArticle.objects.select_related("article"),
            pk=pk,
            article__auteur=_fiche_enseignant(request.user),
        )
        article_pk = illustration.article_id
        illustration.delete()
        messages.success(request, "Illustration retirée.")
        return redirect("website:article_edition", pk=article_pk)


class ArticleSoumettreView(TeacherRoleRequiredMixin, View):
    http_method_names = ["post"]

    def post(self, request, pk):
        article = get_object_or_404(Article, pk=pk, auteur=_fiche_enseignant(request.user))
        try:
            article.soumettre()
        except ValidationError as erreur:
            messages.error(request, erreur.messages[0])
            return redirect("website:article_edition", pk=article.pk)

        from apps.accounts.models import User

        notifier_plusieurs(
            User.objects.filter(is_active=True, role__in=[User.Role.ADMIN, User.Role.SECRETARIAT]),
            f"Article à relire — {article.titre}",
            type_notification=Notification.Type.SYSTEME,
            message=(
                f"{article.auteur.nom_complet} soumet l'article « {article.titre} » à relecture. "
                "Rien ne paraît sous le nom de l'institut sans ce second regard : le texte attend "
                "votre décision, publication ou renvoi en brouillon."
            ),
            details=[
                {"libelle": "Article", "valeur": article.titre},
                {"libelle": "Auteur", "valeur": article.auteur.nom_complet},
            ],
            url_cible=reverse("website:articles_relecture"),
        )
        messages.success(request, "Article soumis à relecture. Vous serez averti de la décision.")
        return redirect("website:mes_articles")


# ══════════════════════════════════════════════
# Le relecteur
# ══════════════════════════════════════════════


class ArticlesRelectureView(StaffRoleRequiredMixin, ListView):
    template_name = "website/articles/relecture.html"
    context_object_name = "articles"
    paginate_by = 25

    def get_queryset(self):
        return Article.objects.filter(
            Q(statut=Article.Statut.RELECTURE) | Q(statut=Article.Statut.PUBLIE)
        ).select_related("auteur")

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        contexte["nav"] = "articles"
        contexte["a_relire"] = [a for a in contexte["articles"] if a.statut == Article.Statut.RELECTURE]
        contexte["publies"] = [a for a in contexte["articles"] if a.est_public]
        return contexte


class ArticleDecisionView(StaffRoleRequiredMixin, View):
    """Publier, renvoyer à l'auteur, ou retirer de la publication."""

    http_method_names = ["post"]

    def post(self, request, pk):
        article = get_object_or_404(Article.objects.select_related("auteur__user"), pk=pk)
        action = request.POST.get("action")

        try:
            if action == "publier":
                article.publier(par=request.user)
                titre_avis, message_avis = "Votre article est publié", article.titre
            elif action == "renvoyer":
                article.renvoyer_en_brouillon(request.POST.get("motif", ""), par=request.user)
                titre_avis, message_avis = "Votre article demande une reprise", article.motif_refus
            elif action == "retirer":
                article.retirer(par=request.user)
                titre_avis, message_avis = "Votre article a été retiré de la publication", article.titre
            else:
                raise ValidationError("Action inconnue.")
        except ValidationError as erreur:
            messages.error(request, erreur.messages[0])
            return redirect("website:articles_relecture")

        journaliser(
            JournalAudit.Action.CHANGEMENT_STATUT,
            utilisateur=request.user,
            request=request,
            objet=article,
            objet_libelle=f"Article « {article.titre} » → {article.get_statut_display()}",
        )
        if article.auteur.user_id:
            notifier(
                article.auteur.user,
                titre_avis,
                type_notification=Notification.Type.SYSTEME,
                message=message_avis,
                url_cible=reverse("website:mes_articles"),
            )
        messages.success(request, f"« {article.titre} » — {article.get_statut_display().lower()}.")
        return redirect("website:articles_relecture")


# ══════════════════════════════════════════════
# Le visiteur
# ══════════════════════════════════════════════


class ArticlesPublicsView(ListView):
    template_name = "website/articles/liste_publique.html"
    context_object_name = "articles"
    paginate_by = 12

    def get_queryset(self):
        requete = Article.objects.filter(statut=Article.Statut.PUBLIE).select_related("auteur")
        recherche = self.request.GET.get("q", "").strip()
        if recherche:
            requete = requete.filter(
                Q(titre__icontains=recherche)
                | Q(sous_titre__icontains=recherche)
                | Q(mots_cles__icontains=recherche)
                | Q(auteur__nom__icontains=recherche)
            )
        return requete

    def get_context_data(self, **kwargs):
        return {**super().get_context_data(**kwargs), "recherche": self.request.GET.get("q", "")}


class ArticlePublicView(DetailView):
    template_name = "website/articles/detail_public.html"
    context_object_name = "article"

    def get_queryset(self):
        # Seuls les articles publiés : un brouillon dont l'adresse fuite ne
        # doit pas être lisible pour autant.
        return (
            Article.objects.filter(statut=Article.Statut.PUBLIE)
            .select_related("auteur")
            .prefetch_related("illustrations")
        )
