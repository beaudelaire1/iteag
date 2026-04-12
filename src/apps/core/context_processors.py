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
