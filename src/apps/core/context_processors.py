from pathlib import Path

from django.conf import settings

from apps.core.navigation import rubriques_pour


def navigation_publique(request):
    """Rubriques de la barre publique, celle de la page courante marquée active.

    Évaluée paresseusement, comme le compteur de notifications : une page qui
    n'affiche pas la barre — un PDF, un fragment HTMX — ne résout aucune URL.
    """
    chemin = getattr(request, "path", "/")
    return {"navigation_publique": lambda: rubriques_pour(chemin)}


def site_context(request):
    """Global template context for all pages."""
    site_url = settings.SITE_URL.rstrip("/")
    fichiers_statiques = (
        Path(settings.BASE_DIR) / "static" / "css" / "main.css",
        Path(settings.BASE_DIR) / "static" / "js" / "iteag.js",
    )
    asset_version = max((fichier.stat().st_mtime_ns for fichier in fichiers_statiques if fichier.exists()), default=1)
    return {
        "SITE_NAME": "ITEAG",
        "SITE_FULL_NAME": "Institut de Théologie Évangélique des Antilles et de la Guyane",
        "SITE_TAGLINE": "Une formation de qualité pour un service efficace",
        "SITE_URL": site_url,
        "CANONICAL_URL": f"{site_url}{request.path}",
        "SITE_EMAIL": "secretariat@iteag.org",
        "SITE_PHONE": "+590 690 37 64 17",
        "SITE_ADDRESS": "201 lot Pointe d'Or, 97139 Les Abymes, Guadeloupe",
        "SITE_FACEBOOK": "https://fr-fr.facebook.com/iteag",
        "SITE_YOUTUBE": "https://www.youtube.com/@formationiteag327",
        "ASSET_VERSION": asset_version,
        "DEBUG": settings.DEBUG,
        "CLOUDFLARE_TURNSTILE_ENABLED": settings.CLOUDFLARE_TURNSTILE_ENABLED,
        "CLOUDFLARE_TURNSTILE_SITE_KEY": settings.CLOUDFLARE_TURNSTILE_SITE_KEY,
    }


def notifications_context(request):
    """Compteur de notifications non lues, pour le bandeau des portails.

    Évalué paresseusement : les pages publiques ne paient pas la requête.
    """
    utilisateur = getattr(request, "user", None)
    if utilisateur is None or not utilisateur.is_authenticated:
        return {}

    from apps.core.services.notifications import compter_non_lues

    return {"notifications_non_lues": lambda: compter_non_lues(utilisateur)}
