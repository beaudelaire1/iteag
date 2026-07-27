from django.urls import path

from apps.commerce import views

app_name = "commerce"

urlpatterns = [
    path("", views.CatalogueView.as_view(), name="catalogue"),
    path("panier/", views.PanierView.as_view(), name="panier"),
    path("panier/ajouter/<uuid:pk>/", views.AjouterPanierView.as_view(), name="panier_ajouter"),
    path("panier/modifier/<uuid:pk>/", views.ModifierPanierView.as_view(), name="panier_modifier"),
    path("panier/retirer/<uuid:pk>/", views.RetirerPanierView.as_view(), name="panier_retirer"),
    path("commander/", views.CommanderView.as_view(), name="commander"),
    path("commande/<uuid:jeton>/", views.CommandeSuiviView.as_view(), name="commande_suivi"),
    path("gestion/", views.GestionCommandesView.as_view(), name="gestion_commandes"),
    path("gestion/commandes/<uuid:pk>/action/", views.CommandeActionView.as_view(), name="commande_action"),
    path("gestion/stock/", views.GestionStockView.as_view(), name="gestion_stock"),
    path("gestion/stock/<uuid:pk>/ajuster/", views.AjusterStockView.as_view(), name="stock_ajuster"),
    path("gestion/livres/ajouter/", views.ProduitCreateView.as_view(), name="produit_ajouter"),
    path("gestion/livres/<uuid:pk>/modifier/", views.ProduitUpdateView.as_view(), name="produit_modifier"),
    path("livre/<slug:slug>/", views.ProduitDetailView.as_view(), name="produit_detail"),
]
