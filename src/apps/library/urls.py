from django.urls import path

from . import views, views_sanctions

app_name = "library"

urlpatterns = [
    path("", views.CatalogueView.as_view(), name="catalogue"),
    path("gestion/", views.GestionNoticesView.as_view(), name="gestion"),
    path("gestion/emprunts/", views.GestionEmpruntsView.as_view(), name="gestion_emprunts"),
    path("gestion/emprunts/creer/", views.EmpruntCreateView.as_view(), name="emprunt_creer"),
    path("gestion/emprunts/<int:pk>/modifier/", views.EmpruntUpdateView.as_view(), name="emprunt_modifier"),
    path("gestion/emprunts/<int:pk>/supprimer/", views.EmpruntDeleteView.as_view(), name="emprunt_supprimer"),
    path("gestion/emprunts/<int:pk>/action/", views.EmpruntActionView.as_view(), name="emprunt_action"),
    path(
        "gestion/suspensions/<int:pk>/lever/",
        views_sanctions.LeverSuspensionView.as_view(),
        name="suspension_lever",
    ),
    path("gestion/nouvelle/", views.NoticeCreateView.as_view(), name="notice_creer"),
    path("gestion/<int:pk>/modifier/", views.NoticeUpdateView.as_view(), name="notice_modifier"),
    path("gestion/<int:pk>/disponibilite/", views.NoticeDisponibiliteView.as_view(), name="notice_disponibilite"),
    path("gestion/<int:pk>/supprimer/", views.NoticeDeleteView.as_view(), name="notice_supprimer"),
    path("notice/<int:pk>/", views.NoticeDetailView.as_view(), name="notice_detail"),
    path("notice/<int:pk>/reserver/", views.ReserverOuvrageView.as_view(), name="notice_reserver"),
    path("notice/<int:pk>/annuler/", views.AnnulerReservationView.as_view(), name="notice_annuler"),
    path("emprunt/<int:pk>/annuler/", views.AnnulerReservationView.as_view(), name="emprunt_annuler"),
    path("mes-emprunts/", views.MesEmpruntsView.as_view(), name="mes_emprunts"),
]
