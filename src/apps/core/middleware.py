"""Politique de sécurité du contenu ajustée pour l'administration Django.

Jazzmin, le thème de « /django-admin/ », écrit ses initialisations directement
dans les pages qu'il rend. Une politique qui refuse les scripts en ligne les
supprime silencieusement : le menu latéral, les listes déroulantes et les
filtres cessent alors de répondre, sans qu'aucune erreur ne s'affiche.

Ces gabarits appartiennent à une dépendance : les corriger reviendrait à en
recopier le contenu et à en assumer la maintenance à chaque montée de version.
On préfère n'assouplir « script-src » que sur ce préfixe, qui n'est ouvert
qu'aux comptes techniques et déjà protégé par la double authentification. Le
reste du site — celui que visitent les étudiants et les visiteurs — conserve la
politique stricte.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from csp.middleware import CSPMiddleware

if TYPE_CHECKING:
    from csp.middleware import PolicyParts
    from django.http import HttpRequest, HttpResponseBase

PREFIXE_ADMIN_DJANGO = "/django-admin/"

# La liste remplace entièrement « script-src » sur ce préfixe. Elle reste
# fermée aux origines tierces : seul le site lui-même peut fournir du script.
SCRIPT_SRC_ADMIN_DJANGO = ["'self'", "'unsafe-inline'"]


class CSPAvecAdminDjango(CSPMiddleware):
    """Applique la politique du site, sauf sur l'administration Django."""

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
