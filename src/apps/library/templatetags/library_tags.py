from django import template
from django.utils import timezone

from apps.library import services
from apps.library.models import SuspensionBibliotheque

register = template.Library()


@register.simple_tag
def etat_bibliotheque(utilisateur):
    if not getattr(utilisateur, "is_authenticated", False):
        return {"bloque": False, "emprunt_retard": None, "suspension": None}
    return services.etat_emprunteur(utilisateur)


@register.simple_tag
def suspensions_actives():
    aujourdhui = timezone.localdate()
    return (
        SuspensionBibliotheque.objects.filter(
            levee_le__isnull=True,
            date_debut__lte=aujourdhui,
            date_fin__gte=aujourdhui,
        )
        .select_related("emprunteur", "emprunt", "emprunt__notice")
        .order_by("-date_fin")
    )
