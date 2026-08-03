from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy

from .views import (
    IteagLoginView,
    IteagLogoutView,
    IteagPasswordResetConfirmView,
    IteagPasswordResetView,
    OTPActivationView,
    OTPVerificationView,
    ProfilView,
)

app_name = "accounts"

urlpatterns = [
    path("connexion/", IteagLoginView.as_view(), name="login"),
    path("deconnexion/", IteagLogoutView.as_view(), name="logout"),
    path("comptes/profil/", ProfilView.as_view(), name="profil"),
    # Double authentification
    path("comptes/securite/activer/", OTPActivationView.as_view(), name="otp_activation"),
    path("comptes/securite/verifier/", OTPVerificationView.as_view(), name="otp_verification"),
    path(
        "mot-de-passe/reinitialiser/",
        IteagPasswordResetView.as_view(
            template_name="accounts/password_reset.html",
            email_template_name="accounts/password_reset_email.txt",
            html_email_template_name="accounts/password_reset_email.html",
            subject_template_name="accounts/password_reset_subject.txt",
            success_url=reverse_lazy("accounts:password_reset_done"),
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
        IteagPasswordResetConfirmView.as_view(
            template_name="accounts/password_reset_confirm.html",
            success_url=reverse_lazy("accounts:password_reset_complete"),
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
