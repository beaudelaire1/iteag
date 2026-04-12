from django.contrib.auth import authenticate
from django.contrib.auth.forms import AuthenticationForm
from django.core.exceptions import ValidationError

from .models import User


class EmailOrUsernameAuthenticationForm(AuthenticationForm):
    error_messages = {
        "invalid_login": "Identifiants invalides. Vérifiez votre email ou votre identifiant, puis votre mot de passe.",
        "inactive": "Ce compte est désactivé.",
    }

    def clean(self):
        username = self.cleaned_data.get("username")
        password = self.cleaned_data.get("password")

        if username and "@" in username:
            matched_user = User.objects.filter(email__iexact=username).only("username").first()
            if matched_user:
                username = matched_user.username
                self.cleaned_data["username"] = username

        if username and password:
            self.user_cache = authenticate(self.request, username=username, password=password)
            if self.user_cache is None:
                raise self.get_invalid_login_error()
            self.confirm_login_allowed(self.user_cache)

        if not username or not password:
            raise ValidationError("Veuillez renseigner vos identifiants.")

        return self.cleaned_data