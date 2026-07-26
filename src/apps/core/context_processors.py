from django.conf import settings


def site_context(request):
    """Global template context for all pages."""
    return {
        "SITE_NAME": "ITEAG",
        "SITE_FULL_NAME": "Institut de Théologie Évangélique des Antilles et de la Guyane",
        "SITE_TAGLINE": "Une formation de qualité pour un service efficace",
        "SITE_EMAIL": "secretariat@iteag.org",
        "SITE_PHONE": "+590 690 37 64 17",
        "SITE_ADDRESS": "201 lot Pointe d'Or, 97139 Les Abymes, Guadeloupe",
        "SITE_FACEBOOK": "https://fr-fr.facebook.com/iteag",
        "SITE_YOUTUBE": "https://www.youtube.com/@formationiteag327",
        "DEBUG": settings.DEBUG,
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
