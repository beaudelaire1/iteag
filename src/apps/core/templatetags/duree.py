"""Filtres d'affichage des durées dans les gabarits."""

from django import template

register = template.Library()


@register.filter
def duree_humaine(secondes):
    """Affiche une durée en minutes ou en heures et minutes.

    Exemples : 2700 s → « 45 min », 3600 s → « 1 h »,
    7920 s → « 2 h 12 min ».
    """
    try:
        total_secondes = max(0, int(secondes or 0))
    except (TypeError, ValueError):
        return ""

    total_minutes = round(total_secondes / 60)
    heures, minutes = divmod(total_minutes, 60)

    if heures and minutes:
        return f"{heures} h {minutes:02d} min"
    if heures:
        return f"{heures} h"
    return f"{minutes} min"
