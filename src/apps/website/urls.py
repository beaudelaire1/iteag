from django.urls import path

from . import views, vues_actualites, vues_articles, vues_temoignages

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
        "espace-enseignant/articles/<int:pk>/demander-le-retrait/",
        vues_articles.ArticleDemandeRetraitView.as_view(),
        name="article_demande_retrait",
    ),
    path(
        "espace-enseignant/articles/<int:pk>/supprimer/",
        vues_articles.ArticleSupprimerView.as_view(),
        name="article_supprimer",
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
    # ── Actualités, côté back-office (direction et secrétariat) ──
    path("espace-admin/actualites/", vues_actualites.ActualitesGestionView.as_view(), name="actualites_gestion"),
    path(
        "espace-admin/actualites/nouvelle/",
        vues_actualites.ActualiteEditionView.as_view(),
        name="actualite_creation",
    ),
    path(
        "espace-admin/actualites/<int:pk>/",
        vues_actualites.ActualiteEditionView.as_view(),
        name="actualite_edition",
    ),
    path(
        "espace-admin/actualites/<int:pk>/decision/",
        vues_actualites.ActualiteDecisionView.as_view(),
        name="actualite_decision",
    ),
    # ── Témoignages étudiants ──
    # Le contenu appartient au domaine website, même si la saisie est présentée
    # dans l'espace étudiant. La validation reste réservée à la direction.
    path("espace-etudiant/temoignage/", vues_temoignages.TemoignageEtudiantView.as_view(), name="temoignage_etudiant"),
    path("espace-admin/temoignages/", vues_temoignages.TemoignageListView.as_view(), name="temoignages_gestion"),
    path(
        "espace-admin/temoignages/decision/",
        vues_temoignages.TemoignageDecisionView.as_view(),
        name="temoignage_decision",
    ),
    # ── Relecture, côté administration ──
    path("espace-admin/articles/", vues_articles.ArticlesRelectureView.as_view(), name="articles_relecture"),
    path(
        "espace-admin/articles/<int:pk>/decision/",
        vues_articles.ArticleDecisionView.as_view(),
        name="article_decision",
    ),
]
