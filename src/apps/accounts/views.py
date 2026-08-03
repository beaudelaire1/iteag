import base64
import io

from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView, LogoutView, PasswordResetConfirmView, PasswordResetView
from django.shortcuts import redirect
from django.urls import reverse
from django.views.generic import TemplateView
from django_otp import login as otp_login

from apps.core.services.audit import journaliser
from apps.core.services.turnstile import MESSAGE_ECHEC, valider_requete

from .forms import EmailOrUsernameAuthenticationForm, MotDePasseForm, ProfilForm
from .otp import appareil_confirme, appareil_en_attente, deux_facteurs_requis
from .services.securite import alerter_du_changement, alerter_du_mot_de_passe, etat_sensible


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


class IteagPasswordResetView(PasswordResetView):
    """Empêche l'automatisation des envois de liens de réinitialisation."""

    def form_valid(self, form):
        if not valider_requete(self.request, action="mot_de_passe"):
            form.add_error(None, MESSAGE_ECHEC)
            return self.form_invalid(form)
        return super().form_valid(form)


class IteagPasswordResetConfirmView(PasswordResetConfirmView):
    """Une réinitialisation aboutie est un changement de mot de passe : elle s'annonce."""

    def form_valid(self, form):
        reponse = super().form_valid(form)
        alerter_du_mot_de_passe(form.user)
        journaliser(
            "modification",
            utilisateur=form.user,
            request=self.request,
            objet=form.user,
            objet_libelle="Réinitialisation du mot de passe",
        )
        return reponse


# ──────────────────────────────────────────────
# Profil
# ──────────────────────────────────────────────


def gabarit_navigation(utilisateur) -> str:
    """Barre latérale correspondant au rôle, pour les écrans transverses.

    Le profil est le premier écran commun aux quatre espaces. Sans cette
    correspondance, il faudrait le dupliquer une fois par portail — et il
    dériverait quatre fois.
    """
    if utilisateur.is_etudiant:
        return "etudiant/partials/student_nav.html"
    if utilisateur.is_enseignant:
        return "lms/partials/teacher_nav.html"
    if utilisateur.is_admin:
        return "administration/partials/admin_nav.html"
    if utilisateur.is_secretariat:
        return "administration/partials/secretariat_nav.html"
    return ""


class ProfilView(LoginRequiredMixin, TemplateView):
    """Coordonnées et mot de passe, pour tous les rôles.

    Deux formulaires sur un même écran, distingués par le nom du bouton :
    changer d'adresse et changer de mot de passe sont deux gestes différents,
    et l'un ne doit pas exiger l'autre.
    """

    template_name = "accounts/profil.html"

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        contexte.setdefault("form_profil", ProfilForm(instance=self.request.user))
        contexte.setdefault("form_mot_de_passe", MotDePasseForm(user=self.request.user))
        navigation = gabarit_navigation(self.request.user)
        contexte.update(
            {
                "gabarit_navigation": navigation,
                "gabarit_navigation_mobile": navigation.replace("nav.html", "nav_mobile.html"),
                "retour": tableau_de_bord(self.request.user) or "/",
                "second_facteur_actif": appareil_confirme(self.request.user) is not None,
                "second_facteur_requis": deux_facteurs_requis(self.request.user),
            }
        )
        return contexte

    def post(self, request, *args, **kwargs):
        if "changer_mot_de_passe" in request.POST:
            return self._mot_de_passe(request)
        return self._coordonnees(request)

    def _coordonnees(self, request):
        # La validation écrit déjà dans l'instance : la photographie se prend avant.
        avant = etat_sensible(request.user)
        form = ProfilForm(request.POST, request.FILES, instance=request.user)
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(form_profil=form))

        form.save()
        modifications = alerter_du_changement(request.user, avant)
        journaliser(
            "modification",
            request=request,
            objet=request.user,
            objet_libelle="Mise à jour du profil",
            champs_sensibles=sorted(modifications),
        )
        messages.success(request, "Vos informations ont été enregistrées.")
        return redirect("accounts:profil")

    def _mot_de_passe(self, request):
        form = MotDePasseForm(user=request.user, data=request.POST)
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(form_mot_de_passe=form))

        form.save()
        # Sans cela, changer son mot de passe déconnecte l'auteur du changement.
        update_session_auth_hash(request, form.user)
        alerter_du_mot_de_passe(request.user)
        journaliser("modification", request=request, objet=request.user, objet_libelle="Changement de mot de passe")
        messages.success(request, "Votre mot de passe a été modifié.")
        return redirect("accounts:profil")


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
