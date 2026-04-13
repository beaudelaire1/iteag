from django.contrib.auth.views import LoginView, LogoutView
from django.urls import reverse

from .forms import EmailOrUsernameAuthenticationForm


class IteagLoginView(LoginView):
    template_name = "accounts/login.html"
    authentication_form = EmailOrUsernameAuthenticationForm
    redirect_authenticated_user = True

    def get_success_url(self):
        user = self.request.user
        if user.is_etudiant:
            return reverse("academics:dashboard")
        if user.is_enseignant:
            return reverse("lms:dashboard")
        if user.is_admin or user.is_secretariat:
            return reverse("administration:dashboard")
        return super().get_success_url()


class IteagLogoutView(LogoutView):
    pass