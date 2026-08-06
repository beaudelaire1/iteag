from django import template

from apps.library import services

register = template.Library()


@register.simple_tag
def etat_bibliotheque(utilisateur):
    if not getattr(utilisateur, "is_authenticated", False):
        return {"bloque": False, "emprunt_retard": None, "suspension": None}
    return services.etat_emprunteur(utilisateur)
