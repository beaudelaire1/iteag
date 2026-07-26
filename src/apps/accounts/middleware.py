"""Application du second facteur pour les comptes administratifs."""

from django.shortcuts import redirect
from django.urls import reverse

from apps.accounts.otp import appareil_confirme, deux_facteurs_requis

# Chemins accessibles sans second facteur : sans quoi l'utilisateur ne pourrait
# ni s'enrôler, ni se déconnecter, ni la supervision interroger la sonde.
PREFIXES_EXEMPTS = (
    "/comptes/securite/",
    "/deconnexion/",
    "/connexion/",
    "/mot-de-passe/",
    "/healthz",
    "/static/",
    "/media/",
)


class Force2FAStaffMiddleware:
    """Redirige les comptes soumis au second facteur tant qu'il n'est pas fourni.

    Placé après OTPMiddleware, qui renseigne `request.user.is_verified()`.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        utilisateur = getattr(request, "user", None)

        if (
            utilisateur is not None
            and utilisateur.is_authenticated
            and deux_facteurs_requis(utilisateur)
            and not request.path.startswith(PREFIXES_EXEMPTS)
        ):
            verifie = getattr(utilisateur, "is_verified", None)
            if verifie is None or not verifie():
                cible = "accounts:otp_verification" if appareil_confirme(utilisateur) else "accounts:otp_activation"
                return redirect(f"{reverse(cible)}?suivant={request.path}")

        return self.get_response(request)
