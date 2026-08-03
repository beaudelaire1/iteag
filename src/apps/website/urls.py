from django.urls import path

from . import views, vues_articles

app_name = "website"

urlpatterns = [
    path("contact/merci/", views.contact_success, name="contact_success"),
    # ── Articles de recherche — lecture publique ──
    path("articles/", vues_articles.ArticlesPublicsView.as_view(), name="articles"),
    path("articles/<slug:slug>/", vues_articles.ArticlePublicView.as_view(), name="article_detail"),
    # ── Rédaction, côté enseignant ──
    path("espace-enseignant/articles/", vues_articles.MesArticlesView.as_view(), name="mes_articles"),
    path(
        "espace-enseignant/articles/nouveau/",
        vues_articles.ArticleEditionView.as_view(),
        name="article_creation",
    ),
    path(
        "espace-enseignant/articles/<int:pk>/",
        vues_articles.ArticleEditionView.as_view(),
        name="article_edition",
    ),
    path(
        "espace-enseignant/articles/<int:pk>/soumettre/",
        vues_articles.ArticleSoumettreView.as_view(),
        name="article_soumettre",
    ),
    path(
        "espace-enseignant/articles/<int:pk>/illustration/",
        vues_articles.IllustrationCreateView.as_view(),
        name="article_illustration",
    ),
    path(
        "espace-enseignant/illustrations/<int:pk>/supprimer/",
        vues_articles.IllustrationDeleteView.as_view(),
        name="illustration_supprimer",
    ),
    # ── Relecture, côté administration ──
    path("espace-admin/articles/", vues_articles.ArticlesRelectureView.as_view(), name="articles_relecture"),
    path(
        "espace-admin/articles/<int:pk>/decision/",
        vues_articles.ArticleDecisionView.as_view(),
        name="article_decision",
    ),
]
