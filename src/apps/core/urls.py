from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
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
