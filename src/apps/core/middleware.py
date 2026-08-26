"""Middlewares transverses du socle ITEAG."""

from __future__ import annotations

import os
import time
from typing import TYPE_CHECKING

from csp.middleware import CSPMiddleware
from django.conf import settings
from django.utils.cache import patch_cache_control

if TYPE_CHECKING:
    from csp.middleware import PolicyParts
    from django.http import HttpRequest, HttpResponseBase

PREFIXE_ADMIN_DJANGO = "/django-admin/"
HOTES_INDEXABLES = frozenset({"iteag.org", "www.iteag.org"})
PERMISSIONS_POLICY = "camera=(), microphone=(), geolocation=(), usb=()"
ENTETE_REVISION = "X-ITEAG-Revision"
VARIABLE_REVISION = "ITEAG_REVISION"

# La liste remplace entièrement « script-src » sur ce préfixe. Elle reste
# fermée aux origines tierces : seul le site lui-même peut fournir du script.
SCRIPT_SRC_ADMIN_DJANGO = ["'self'", "'unsafe-inline'"]


class CSPAvecAdminDjango(CSPMiddleware):
    """Applique la politique CSP et les garde-fous HTTP transverses.

    Jazzmin écrit certaines initialisations directement dans ses pages. On
    limite donc l'assouplissement CSP à /django-admin/, déjà réservé au
    personnel et protégé par le second facteur ; le reste du site conserve la
    politique stricte.

    La politique interdit aussi tout embarquement de l'application via
    ``frame-ancestors 'none'``. C'est la défense CSP moderne qui complète
    ``X-Frame-Options: DENY`` sans toucher aux iframes que l'application charge
    elle-même via ``frame-src`` (Turnstile et la carte OpenStreetMap).

    Toute origine autre que les deux domaines publics reçoit enfin un
    X-Robots-Tag bloquant l'indexation : une préproduction sslip.io ne peut pas
    être indexée par oubli de configuration du proxy.

    Le déploiement fournit ``ITEAG_REVISION`` à partir du ``SOURCE_COMMIT``
    prédéfini par Coolify. Ce nom applicatif évite de redéclarer et d'écraser la
    variable prédéfinie elle-même. Sa valeur est exposée dans un en-tête non
    sensible afin qu'un contrôle externe puisse prouver quelle révision répond
    réellement derrière l'URL de préproduction.
    """

    def get_policy_parts(
        self,
        request: HttpRequest,
        response: HttpResponseBase,
        report_only: bool = False,
    ) -> PolicyParts:
        parties = super().get_policy_parts(request=request, response=response, report_only=report_only)
        remplacements = dict(parties.replace or {})
        remplacements.setdefault("frame-ancestors", ["'none'"])
        if request.path_info.startswith(PREFIXE_ADMIN_DJANGO):
            # Une vue qui aurait déjà exprimé sa propre exigence reste prioritaire.
            remplacements.setdefault("script-src", SCRIPT_SRC_ADMIN_DJANGO)
        parties.replace = remplacements
        return parties

    def process_response(self, request: HttpRequest, response: HttpResponseBase) -> HttpResponseBase:
        response = super().process_response(request, response)
        response.headers["Permissions-Policy"] = PERMISSIONS_POLICY

        revision = os.environ.get(VARIABLE_REVISION, "").strip()
        if revision:
            response.headers[ENTETE_REVISION] = revision

        # Le HTML authentifié contient des éléments propres à la session
        # (identité, rôle, notifications, liens d'espace). Même si aucun cache
        # applicatif de page n'est utilisé, on interdit explicitement à un proxy
        # partagé de conserver cette réponse et de la resservir à un autre
        # utilisateur.
        utilisateur = getattr(request, "user", None)
        if utilisateur is not None and utilisateur.is_authenticated:
            patch_cache_control(
                response,
                private=True,
                no_cache=True,
                no_store=True,
                must_revalidate=True,
            )

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
