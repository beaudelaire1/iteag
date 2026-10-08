import base64
import io
import time

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView, LogoutView, PasswordResetConfirmView, PasswordResetView
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.crypto import constant_time_compare
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View
from django.views.generic import TemplateView
from django_otp import login as otp_login
from django_otp import verify_token as verifier_otp
from django_otp.oath import TOTP
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.core.mixins import StaffRoleRequiredMixin
from apps.core.services.audit import journaliser
from apps.core.services.turnstile import MESSAGE_ECHEC, valider_requete

from .forms import EmailOrUsernameAuthenticationForm, MotDePasseForm, ProfilForm, SignatureForm
from .models import User
from .otp import appareil_confirme, appareil_en_attente, appareils_confirmes, deux_facteurs_requis, empreinte_appareil
from .services.securite import alerter_du_changement, alerter_du_mot_de_passe, etat_sensible


def tableau_de_bord(utilisateur) -> str:
    """Espace d'accueil correspondant au rôle. Un seul endroit en décide."""
    if utilisateur.is_etudiant and hasattr(utilisateur, "profil_etudiant"):
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
        reponse = super().form_invalid(form)
        reponse.context_data["essais_restants"] = self._essais_restants(form)
        return reponse

    def _essais_restants(self, form) -> int | None:
        """Essais avant le verrouillage, annoncés quand il en reste peu.

        Le blocage tombait sans prévenir : au cinquième échec, la personne qui
        se trompait d'une majuscule perdait l'accès pendant une demi-heure
        sans avoir été avertie qu'il approchait.
        """
        identifiant = form.data.get("username", "").strip()
        if not identifiant or not getattr(settings, "AXES_ENABLED", True):
            return None
        from axes.handlers.proxy import AxesProxyHandler

        echecs = AxesProxyHandler.get_failures(self.request, {"username": identifiant})
        restants = settings.AXES_FAILURE_LIMIT - echecs
        return restants if 0 < restants <= 2 else None

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
    if utilisateur.is_etudiant and hasattr(utilisateur, "profil_etudiant"):
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


class SignatureView(StaffRoleRequiredMixin, TemplateView):
    template_name = "accounts/signature.html"

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        contexte.setdefault("form", SignatureForm(instance=self.request.user))
        navigation = gabarit_navigation(self.request.user)
        contexte.update(
            {
                "nav": "signature",
                "gabarit_navigation": navigation,
                "gabarit_navigation_mobile": navigation.replace("nav.html", "nav_mobile.html"),
                "retour": tableau_de_bord(self.request.user) or "/",
            }
        )
        return contexte

    def post(self, request, *args, **kwargs):
        ancien_nom = request.user.signature.name
        ancien_stockage = request.user.signature.storage
        form = SignatureForm(request.POST, request.FILES, instance=request.user)
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(form=form))

        utilisateur = form.save()
        if ancien_nom and ancien_nom != utilisateur.signature.name:
            ancien_stockage.delete(ancien_nom)
        journaliser(
            "modification",
            request=request,
            objet=request.user,
            objet_libelle="Mise à jour de la signature numérique",
        )
        messages.success(request, "Votre signature numérique a été enregistrée.")
        return redirect("accounts:signature")


# ──────────────────────────────────────────────
# Double authentification
# ──────────────────────────────────────────────


class _BaseOTPView(LoginRequiredMixin, TemplateView):
    @staticmethod
    def code_saisi(request) -> str:
        # Les applications copient aussi des espaces insécables et fines.
        return "".join(request.POST.get("code", "").split())

    def suivant(self) -> str:
        propose = self.request.GET.get("suivant") or self.request.POST.get("suivant") or ""
        # Une redirection ouverte transformerait cette page en tremplin.
        if propose.startswith("/") and not propose.startswith("//"):
            return propose
        return tableau_de_bord(self.request.user) or "/"

    @staticmethod
    def _attente_avant_nouvel_essai(appareil) -> int:
        """Retourne le délai de throttling restant, sans confondre attente et mauvais code."""
        autorise, donnees = appareil.verify_is_allowed()
        if autorise:
            return 0
        verrou_jusqua = (donnees or {}).get("locked_until")
        if verrou_jusqua is None:
            return 1
        secondes = (verrou_jusqua - timezone.now()).total_seconds()
        return max(1, int(secondes) + 1)

    @staticmethod
    def _correspond_a_un_code_totp(appareil, code: str) -> bool:
        """Détecte un code TOTP authentique déjà consommé, sans le réaccepter."""
        try:
            jeton = int(code)
        except (TypeError, ValueError):
            return False
        totp = TOTP(appareil.bin_key, appareil.step, appareil.t0, appareil.digits, appareil.drift)
        totp.time = time.time()
        return totp.verify(jeton, appareil.tolerance)

    def _message_echec_code(self, appareils, code: str) -> None:
        if any(self._correspond_a_un_code_totp(appareil, code) for appareil in appareils):
            messages.error(
                self.request,
                "Ce code a déjà été utilisé. Attendez le prochain code affiché par votre application, puis réessayez.",
            )
        else:
            messages.error(
                self.request,
                "Code incorrect ou expiré. Vérifiez que la date et l’heure du téléphone sont réglées automatiquement.",
            )


class OTPActivationView(_BaseOTPView):
    """Enrôlement d'un appareil TOTP : QR code, secret, puis vérification."""

    template_name = "accounts/otp_activation.html"
    CLE_ENROLEMENT = "otp_enrolement"

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and appareil_confirme(request.user):
            return redirect(reverse("accounts:otp_verification"))
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        appareil = appareil_en_attente(self.request.user)
        empreinte = empreinte_appareil(appareil)
        self.request.session[self.CLE_ENROLEMENT] = {"id": appareil.pk, "empreinte": empreinte}
        contexte.update(
            {
                "qr_code_base64": self._qr_code(appareil.config_url),
                "appareil_enrolement": f"{appareil.pk}:{empreinte}",
                "secret_manuel": self._secret_lisible(appareil),
                "obligatoire": deux_facteurs_requis(self.request.user),
                "suivant": self.suivant(),
                "chiffres": appareil.digits,
                "longueur_code": appareil.digits + 3,
                "motif_code": rf"[0-9\s]{{{appareil.digits},{appareil.digits + 3}}}",
            }
        )
        return contexte

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        User.objects.select_for_update().get(pk=request.user.pk)
        if appareil_confirme(request.user) is not None:
            return redirect(reverse("accounts:otp_verification"))
        enrolement = request.session.get(self.CLE_ENROLEMENT, {})
        appareil = (
            TOTPDevice.objects.select_for_update()
            .filter(user=request.user, confirmed=False, pk=enrolement.get("id"))
            .first()
        )
        if (
            appareil is None
            or not constant_time_compare(
                request.POST.get("appareil", ""), f"{enrolement.get('id')}:{enrolement.get('empreinte')}"
            )
            or not constant_time_compare(enrolement.get("empreinte", ""), empreinte_appareil(appareil))
        ):
            messages.warning(
                request,
                "La configuration du second facteur a changé. Scannez le QR code affiché ci-dessous, "
                "puis saisissez le nouveau code de votre application.",
            )
            return self.render_to_response(self.get_context_data(**kwargs))
        code = self.code_saisi(request)

        attente = self._attente_avant_nouvel_essai(appareil)
        if attente:
            messages.warning(
                request,
                f"Trop de tentatives rapprochées. Réessayez dans {attente} seconde{'s' if attente > 1 else ''}.",
            )
            return self.render_to_response(self.get_context_data(**kwargs))

        appareil_verifie = verifier_otp(request.user, appareil.persistent_id, code)
        if appareil_verifie is not None:
            appareil_verifie.confirmed = True
            appareil_verifie.save(update_fields=["confirmed"])
            request.session.pop(self.CLE_ENROLEMENT, None)
            otp_login(request, appareil_verifie)
            journaliser("modification", request=request, objet_libelle="Activation du second facteur")
            messages.success(request, "Double authentification activée.")
            return redirect(self.suivant())

        self._message_echec_code([appareil], code)
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
        chiffres_disponibles = sorted({appareil.digits for appareil in appareils_confirmes(self.request.user)}) or [6]
        minimum, maximum = chiffres_disponibles[0], chiffres_disponibles[-1]
        return {
            **super().get_context_data(**kwargs),
            "suivant": self.suivant(),
            "chiffres": " ou ".join(str(chiffres) for chiffres in chiffres_disponibles),
            "longueur_code": maximum + 3,
            "motif_code": rf"[0-9\s]{{{minimum},{maximum + 3}}}",
        }

    def post(self, request, *args, **kwargs):
        code = self.code_saisi(request)
        appareils = list(appareils_confirmes(request.user))

        if not appareils:
            return redirect(reverse("accounts:otp_activation"))

        attentes = []
        essai_effectue = False

        # Un compte peut avoir plusieurs appareils confirmés après un ancien
        # enrôlement. Le code doit être accepté s'il correspond à l'un d'eux :
        # bloquer sur le premier appareil rendrait un code parfaitement valide
        # inutilisable dès qu'un appareil obsolète subsiste en base.
        for appareil in appareils:
            attente = self._attente_avant_nouvel_essai(appareil)
            if attente:
                attentes.append(attente)
                continue

            essai_effectue = True
            appareil_verifie = verifier_otp(request.user, appareil.persistent_id, code)
            if appareil_verifie is not None:
                otp_login(request, appareil_verifie)
                return redirect(self.suivant())

        if not essai_effectue and attentes:
            attente = min(attentes)
            journaliser("connexion_echec", request=request, objet_libelle="Second facteur temporairement limité")
            messages.warning(
                request,
                f"Trop de tentatives rapprochées. Réessayez dans {attente} seconde{'s' if attente > 1 else ''}.",
            )
            return self.render_to_response(self.get_context_data(**kwargs))

        journaliser("connexion_echec", request=request, objet_libelle="Second facteur invalide")
        self._message_echec_code(appareils, code)
        return self.render_to_response(self.get_context_data(**kwargs))


class AffichageView(LoginRequiredMixin, View):
    """Bascule entre l'affichage confortable et l'affichage compact.

    Le choix revient à la page d'où il a été fait : on change d'affichage parce
    que l'écran présent gêne, pas pour aller régler un profil.
    """

    http_method_names = ["post"]

    def post(self, request):
        from .models import User

        choix = request.POST.get("affichage")
        if choix in User.Affichage.values and choix != request.user.affichage:
            request.user.affichage = choix
            request.user.save(update_fields=["affichage"])
            if choix == User.Affichage.COMPACT:
                messages.info(
                    request, "Affichage compact activé. Le bouton en bas du menu permet de revenir en arrière."
                )
            else:
                messages.info(request, "Affichage confortable activé : grands caractères et menus dépliés.")

        suivant = request.POST.get("suivant", "")
        if not url_has_allowed_host_and_scheme(
            suivant, allowed_hosts={request.get_host()}, require_https=request.is_secure()
        ):
            suivant = tableau_de_bord(request.user) or reverse("accounts:profil")
        return redirect(suivant)


class VoletView(LoginRequiredMixin, View):
    """Masque ou réaffiche le volet de navigation des espaces privés.

    Le script bascule l'affichage aussitôt et enregistre le choix en tâche de
    fond ; sans script, le bouton envoie le formulaire et la page revient.
    """

    http_method_names = ["post"]

    def post(self, request):
        masque = request.POST.get("volet") == "masque"
        if request.user.volet_masque != masque:
            request.user.volet_masque = masque
            request.user.save(update_fields=["volet_masque"])
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return HttpResponse(status=204)
        suivant = request.POST.get("suivant", "")
        if not url_has_allowed_host_and_scheme(
            suivant, allowed_hosts={request.get_host()}, require_https=request.is_secure()
        ):
            suivant = tableau_de_bord(request.user) or reverse("accounts:profil")
        return redirect(suivant)


class SessionActiveView(LoginRequiredMixin, View):
    """Prolonge la session de quelqu'un qui travaille sans changer de page.

    Taper une longue réponse ne fait aucune requête : la session expirait au
    milieu de la saisie, et l'enregistrement renvoyait vers la connexion en
    perdant le texte. Le script n'appelle cette adresse que si la personne a
    tapé, cliqué ou fait défiler récemment — une vraie inactivité de trente
    minutes ferme toujours la session, comme le prévoit le cahier des charges.
    """

    http_method_names = ["post"]

    def post(self, request):
        # « SESSION_SAVE_EVERY_REQUEST » repousse l'échéance à chaque requête :
        # il suffit de répondre.
        return HttpResponse(status=204)


class AideView(LoginRequiredMixin, TemplateView):
    """Mode d'emploi des tâches courantes, rédigé pour qui n'est pas du métier."""

    template_name = "accounts/aide.html"

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        navigation = gabarit_navigation(self.request.user)
        utilisateur = self.request.user
        contexte.update(
            {
                "gabarit_navigation": navigation,
                "gabarit_navigation_mobile": navigation.replace("nav.html", "nav_mobile.html"),
                "personnel": utilisateur.is_admin or utilisateur.is_secretariat,
            }
        )
        return contexte
