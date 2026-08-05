from django.urls import path

from . import views
from .vues_editeur_riche import LienExterneEditeurView

app_name = "core"

urlpatterns = [
    path(
        "editeur-riche/lien/",
        LienExterneEditeurView.as_view(),
        name="editeur_lien_externe",
    ),
    # Notifications
    path("notifications/", views.NotificationListView.as_view(), name="notifications"),
    path(
        "notifications/<int:pk>/lue/",
        views.NotificationMarquerLueView.as_view(),
        name="notification_lue",
    ),
    path(
        "notifications/tout-lire/",
        views.NotificationToutMarquerLuView.as_view(),
        name="notifications_tout_lire",
    ),
    path(
        "notifications/<int:pk>/supprimer/",
        views.NotificationSupprimerView.as_view(),
        name="notification_supprimer",
    ),
    path(
        "notifications/supprimer-lues/",
        views.NotificationToutSupprimerView.as_view(),
        name="notifications_supprimer_lues",
    ),
    # Newsletter
    path("newsletter/inscription/", views.NewsletterInscriptionView.as_view(), name="newsletter_inscription"),
    path(
        "newsletter/confirmation/<str:token>/",
        views.NewsletterConfirmationView.as_view(),
        name="newsletter_confirmation",
    ),
    path(
        "newsletter/desinscription/<str:token>/",
        views.NewsletterDesinscriptionView.as_view(),
        name="newsletter_desinscription",
    ),
]
