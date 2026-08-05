"""Le socle JavaScript qu'exigent les bundles Wagtail hors de l'administration.

« draftail.js », les adaptateurs telepath et les sélecteurs supposent que
« vendor.js » et ses dépendances sont déjà chargés — dans l'administration,
elles le sont toujours. Servis seuls dans un portail, ces bundles s'exécutent
sans rien enregistrer : telepath reste vide, le champ ne se construit pas, et
l'envoi du formulaire part amputé.

La liste est celle de « DraftailPortail.media », dans le même ordre. La tenir
à deux endroits finirait par les faire diverger ; ce module est donc l'endroit
unique, et le widget d'éditeur riche pourra s'y brancher à son tour.
"""

from django import template
from django.utils.html import format_html_join
from wagtail.admin.staticfiles import versioned_static

register = template.Library()

SOCLE = (
    "wagtailadmin/js/vendor/jquery-3.6.0.min.js",
    "wagtailadmin/js/vendor/bootstrap-transition.js",
    "wagtailadmin/js/vendor/bootstrap-modal.js",
    "wagtailadmin/js/vendor.js",
    "wagtailadmin/js/modal-workflow.js",
)


@register.simple_tag
def wagtail_socle_portail():
    """Les balises de script du socle, dans l'ordre où elles doivent venir."""
    return format_html_join("\n", '<script src="{}"></script>', ((versioned_static(chemin),) for chemin in SOCLE))
