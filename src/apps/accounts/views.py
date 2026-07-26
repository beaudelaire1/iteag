import base64
import io

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView, LogoutView
from django.shortcuts import redirect
from django.urls import reverse
from django.views.generic import TemplateView
from django_otp import login as otp_login

from apps.core.services.audit import journaliser

from .forms import EmailOrUsernameAuthenticationForm
from .otp import appareil_confirme, appareil_en_attente, deux_facteurs_requis


def tableau_de_bord(utilisateur) -> str:
    """Espace d'accueil correspondant au rôle. Un seul endroit en décide."""
    if utilisateur.is_etudiant:
        return reverse("etudiant:dashboard")
    if utilisateur.is_enseignant:
        # L'accueil unifié, et non l'un des deux tableaux de bord partiels :
        # l'enseignant ne pense pas « présentiel » et « vidéo » séparément.
        return reverse("enseignant:accueil")
    if utilisateur.is_admin:
        return reverse("administration:dashboard")
    if utilisateur.is_secretariat:
        return reverse("secretariat:dashboard")
    return ""


class IteagLoginView(LoginView):
    template_name = "accounts/login.html"
    authentication_form = EmailOrUsernameAuthenticationForm
    redirect_authenticated_user = True

    def form_valid(self, form):
        reponse = super().form_valid(form)
        journaliser("connexion", request=self.request, utilisateur=self.request.user)
        return reponse

    def form_invalid(self, form):
        journaliser(
            "connexion_echec",
            request=self.request,
            objet_libelle=form.data.get("username", "")[:250],
        )
        return super().form_invalid(form)

    def get_success_url(self):
        cible = tableau_de_bord(self.request.user)
        return cible or super().get_success_url()


class IteagLogoutView(LogoutView):
    pass


# ──────────────────────────────────────────────
# Double authentification
# ──────────────────────────────────────────────


class _BaseOTPView(LoginRequiredMixin, TemplateView):
    def suivant(self) -> str:
        propose = self.request.GET.get("suivant") or self.request.POST.get("suivant") or ""
        # Une redirection ouverte transformerait cette page en tremplin.
        if propose.startswith("/") and not propose.startswith("//"):
            return propose
        return tableau_de_bord(self.request.user) or "/"


class OTPActivationView(_BaseOTPView):
    """Enrôlement d'un appareil TOTP : QR code, secret, puis vérification."""

    template_name = "accounts/otp_activation.html"

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and appareil_confirme(request.user):
            return redirect(reverse("accounts:otp_verification"))
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        appareil = appareil_en_attente(self.request.user)
        contexte.update(
            {
                "qr_code_base64": self._qr_code(appareil.config_url),
                "secret_manuel": self._secret_lisible(appareil),
                "obligatoire": deux_facteurs_requis(self.request.user),
                "suivant": self.suivant(),
            }
        )
        return contexte

    def post(self, request, *args, **kwargs):
        appareil = appareil_en_attente(request.user)
        code = request.POST.get("code", "").strip().replace(" ", "")

        if appareil.verify_token(code):
            appareil.confirmed = True
            appareil.save(update_fields=["confirmed"])
            otp_login(request, appareil)
            journaliser("modification", request=request, objet_libelle="Activation du second facteur")
            messages.success(request, "Double authentification activée.")
            return redirect(self.suivant())

        messages.error(request, "Code incorrect. Vérifiez l'heure de votre téléphone et réessayez.")
        return self.render_to_response(self.get_context_data(**kwargs))

    @staticmethod
    def _qr_code(url: str) -> str:
        """QR encodé en base64 : aucun appel réseau, compatible avec la CSP."""
        import qrcode

        image = qrcode.make(url, box_size=6, border=2)
        tampon = io.BytesIO()
        image.save(tampon, format="PNG")
        return base64.b64encode(tampon.getvalue()).decode()

    @staticmethod
    def _secret_lisible(appareil) -> str:
        """Secret en base32, groupé par quatre pour la saisie manuelle."""
        secret = base64.b32encode(appareil.bin_key).decode().rstrip("=")
        return " ".join(secret[i : i + 4] for i in range(0, len(secret), 4))


class OTPVerificationView(_BaseOTPView):
    """Saisie du code à usage unique une fois l'appareil enrôlé."""

    template_name = "accounts/otp_verification.html"

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and not appareil_confirme(request.user):
            return redirect(reverse("accounts:otp_activation"))
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        return {**super().get_context_data(**kwargs), "suivant": self.suivant()}

    def post(self, request, *args, **kwargs):
        appareil = appareil_confirme(request.user)
        code = request.POST.get("code", "").strip().replace(" ", "")

        if appareil is not None and appareil.verify_token(code):
            otp_login(request, appareil)
            return redirect(self.suivant())

        journaliser("connexion_echec", request=request, objet_libelle="Second facteur invalide")
        messages.error(request, "Code incorrect ou expiré.")
        return self.render_to_response(self.get_context_data(**kwargs))
