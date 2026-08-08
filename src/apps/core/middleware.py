"""Middlewares transverses du socle ITEAG."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from csp.middleware import CSPMiddleware
from django.conf import settings

if TYPE_CHECKING:
    from csp.middleware import PolicyParts
    from django.http import HttpRequest, HttpResponseBase

PREFIXE_ADMIN_DJANGO = "/django-admin/"
HOTES_INDEXABLES = frozenset({"iteag.org", "www.iteag.org"})

# La liste remplace entièrement « script-src » sur ce préfixe. Elle reste
# fermée aux origines tierces : seul le site lui-même peut fournir du script.
SCRIPT_SRC_ADMIN_DJANGO = ["'self'", "'unsafe-inline'"]


class CSPAvecAdminDjango(CSPMiddleware):
    """Applique la politique CSP et les garde-fous SEO d'environnement.

    Jazzmin écrit certaines initialisations directement dans ses pages. On
    limite donc l'assouplissement CSP à /django-admin/, déjà réservé au
    personnel et protégé par le second facteur ; le reste du site conserve la
    politique stricte.

    Le même middleware voit toutes les réponses et connaît l'hôte réellement
    demandé. Toute origine autre que les deux domaines publics reçoit donc un
    X-Robots-Tag bloquant l'indexation : une préproduction sslip.io ne peut pas
    être indexée par oubli de configuration du proxy.
    """

    def get_policy_parts(
        self,
        request: HttpRequest,
        response: HttpResponseBase,
        report_only: bool = False,
    ) -> PolicyParts:
        parties = super().get_policy_parts(request=request, response=response, report_only=report_only)
        if not request.path_info.startswith(PREFIXE_ADMIN_DJANGO):
            return parties
        remplacements = dict(parties.replace or {})
        # Une vue qui aurait déjà exprimé sa propre exigence reste prioritaire.
        remplacements.setdefault("script-src", SCRIPT_SRC_ADMIN_DJANGO)
        parties.replace = remplacements
        return parties

    def process_response(self, request: HttpRequest, response: HttpResponseBase) -> HttpResponseBase:
        response = super().process_response(request, response)
        hote = request.get_host().split(":", 1)[0].lower()
        if hote not in HOTES_INDEXABLES:
            response.headers["X-Robots-Tag"] = "noindex, nofollow, noarchive"
        return response


class RafraichissementSessionMiddleware:
    """Conserve une expiration glissante sans écrire la session à chaque requête.

    Django ne réécrit normalement une session que lorsqu'elle est modifiée.
    ``SESSION_SAVE_EVERY_REQUEST`` donnait bien une expiration après 30 minutes
    d'inactivité, mais au prix d'une écriture PostgreSQL pour chaque ressource
    ou page authentifiée. Ici, on ne touche la session qu'à intervalles réguliers
    (5 minutes par défaut) : l'expiration reste glissante, avec une charge
    d'écriture bornée et prévisible.
    """

    CLE_DERNIER_RAFRAICHISSEMENT = "_iteag_session_refresh"

    def __init__(self, get_response):
        self.get_response = get_response
        self.intervalle = max(int(getattr(settings, "SESSION_REFRESH_INTERVAL", 300)), 60)

    def __call__(self, request):
        utilisateur = getattr(request, "user", None)
        session = getattr(request, "session", None)
        if utilisateur is not None and utilisateur.is_authenticated and session is not None:
            maintenant = int(time.time())
            dernier = int(session.get(self.CLE_DERNIER_RAFRAICHISSEMENT, 0) or 0)
            if maintenant - dernier >= self.intervalle:
                session[self.CLE_DERNIER_RAFRAICHISSEMENT] = maintenant

        return self.get_response(request)
