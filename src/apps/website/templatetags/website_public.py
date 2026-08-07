from django import template

from apps.website.models_publications import TemoignageEtudiant

register = template.Library()


@register.inclusion_tag("website/partials/temoignages_etudiants.html")
def temoignages_publics(limite=6):
    """Expose uniquement ce que la direction a explicitement publié."""
    temoignages = (
        TemoignageEtudiant.objects.filter(
            statut=TemoignageEtudiant.Statut.PUBLIE,
            consentement_publication=True,
        )
        .select_related("etudiant")
        .order_by("-valide_le", "-soumis_le")[:limite]
    )
    return {"temoignages_etudiants": temoignages}
