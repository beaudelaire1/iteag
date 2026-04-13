from django.contrib.auth import views as auth_views
from django.urls import path

from .views import IteagLoginView, IteagLogoutView

app_name = "accounts"

urlpatterns = [
    path("connexion/", IteagLoginView.as_view(), name="login"),
    path("deconnexion/", IteagLogoutView.as_view(), name="logout"),
    path(
        "mot-de-passe/reinitialiser/",
        auth_views.PasswordResetView.as_view(
            template_name="accounts/password_reset.html",
            email_template_name="accounts/password_reset_email.txt",
            subject_template_name="accounts/password_reset_subject.txt",
            success_url="/comptes/mot-de-passe/envoye/",
        ),
        name="password_reset",
    ),
    path(
        "mot-de-passe/envoye/",
        auth_views.PasswordResetDoneView.as_view(
            template_name="accounts/password_reset_done.html",
        ),
        name="password_reset_done",
    ),
    path(
        "mot-de-passe/confirmer/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            template_name="accounts/password_reset_confirm.html",
            success_url="/comptes/mot-de-passe/termine/",
        ),
        name="password_reset_confirm",
    ),
    path(
        "mot-de-passe/termine/",
        auth_views.PasswordResetCompleteView.as_view(
            template_name="accounts/password_reset_complete.html",
        ),
        name="password_reset_complete",
    ),
]