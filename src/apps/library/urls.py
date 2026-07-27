from django.urls import path

from . import views

app_name = "library"

urlpatterns = [
    path("", views.CatalogueView.as_view(), name="catalogue"),
    # « gestion » précède « notice/<pk> » sans ambiguïté, mais l'ordre reste
    # explicite : les routes de back-office se lisent groupées.
    path("gestion/", views.GestionNoticesView.as_view(), name="gestion"),
    path("gestion/nouvelle/", views.NoticeCreateView.as_view(), name="notice_creer"),
    path("gestion/<int:pk>/modifier/", views.NoticeUpdateView.as_view(), name="notice_modifier"),
    path("gestion/<int:pk>/disponibilite/", views.NoticeDisponibiliteView.as_view(), name="notice_disponibilite"),
    path("gestion/<int:pk>/supprimer/", views.NoticeDeleteView.as_view(), name="notice_supprimer"),
    path("notice/<int:pk>/", views.NoticeDetailView.as_view(), name="notice_detail"),
]
