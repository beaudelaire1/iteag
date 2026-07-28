"""
Assouplissement ciblé de la politique de sécurité pour la lecture vidéo.

La politique globale reste `frame-src 'none'` et `script-src 'self'`. Ouvrir
ces directives pour tout le site afin que deux pages lisent une vidéo serait
disproportionné : l'ouverture est posée sur les seules vues concernées.

Aucun script tiers n'est autorisé, dans aucun cas. Le lecteur HLS est
auto-hébergé ; les fournisseurs en cadre exécutent leur code dans leur propre
origine, ce que `frame-src` couvre sans toucher à `script-src`.

Les directives sont calculées **à chaque requête**, pas au chargement du
module : figées à l'import, elles ignoreraient tout changement de
configuration et ne seraient pas vérifiables en test.
"""

from apps.elearning.diffusion import origines_actives


def directives_video() -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """
    Directives à poser sur les vues qui lisent une vidéo.

    Retourne ce qui s'ajoute et ce qui se remplace.

    `media-src` et `connect-src` s'ajoutent : le lecteur récupère le manifeste
    et les segments depuis l'origine du fournisseur, en plus de nos propres
    ressources. `frame-src` se **remplace**, car la valeur globale est
    `'none'` : la spécification CSP veut que `'none'` soit seul, et l'associer
    à une origine donne un comportement qui dépend du navigateur.
    """
    origines = origines_actives()
    if not origines:
        return {}, {}
    ajouts = {
        "media-src": ["'self'", "blob:", *origines],
        "connect-src": ["'self'", *origines],
    }
    remplacements = {"frame-src": list(origines)}
    return ajouts, remplacements


class CspLectureVideoMixin:
    """
    Pose l'ouverture CSP sur la réponse, d'après la configuration courante.

    `django-csp` lit les attributs `_csp_update` et `_csp_replace` de la
    réponse ; les poser ici revient à appliquer ses décorateurs, mais avec des
    valeurs calculées au moment de la requête.
    """

    def dispatch(self, request, *args, **kwargs):
        reponse = super().dispatch(request, *args, **kwargs)
        ajouts, remplacements = directives_video()
        if ajouts:
            reponse._csp_update = ajouts
        if remplacements:
            reponse._csp_replace = remplacements
        # La politique globale « same-origin » supprime le Referer sur toute
        # requête sortante — y compris celles du lecteur vers le CDN. Or la
        # zone Bunny vérifie le domaine d'origine (anti-hotlink) en plus du
        # jeton : sans Referer, chaque manifeste est refusé en 403 alors que
        # la signature est valable. On ne rétablit ici que l'origine, jamais
        # le chemin, et seulement sur les pages qui lisent une vidéo.
        # `SecurityMiddleware` pose la politique globale par `setdefault` :
        # la valeur écrite ici reste prioritaire.
        reponse.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return reponse
