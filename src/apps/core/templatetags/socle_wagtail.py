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
from django.utils.html import format_html, format_html_join
from django.utils.safestring import mark_safe
from wagtail.admin.staticfiles import versioned_static

register = template.Library()

SOCLE = (
    "wagtailadmin/js/vendor/jquery-3.6.0.min.js",
    "wagtailadmin/js/vendor/bootstrap-transition.js",
    "wagtailadmin/js/vendor/bootstrap-modal.js",
    "wagtailadmin/js/vendor.js",
    "wagtailadmin/js/modal-workflow.js",
)


@register.simple_tag(takes_context=True)
def wagtail_socle_portail(context):
    """La configuration Wagtail, puis les scripts du socle, dans cet ordre.

    « vendor.js » commence par lire l'élément « wagtail-config » et le passer à
    « JSON.parse ». Absent, il lève « Unexpected end of JSON input » et abandonne
    **avant** de créer « window.telepath » — d'où une cascade de « Cannot read
    properties of undefined (reading 'register') » sur tous les bundles suivants,
    et un champ qui ne se construit jamais.

    Rien dans ces messages ne désigne la configuration manquante : c'est ce qui
    a rendu ce défaut long à cerner. Le gabarit « admin_base.html » de Wagtail
    l'émet juste avant ses scripts ; un portail doit faire de même.
    """
    import json

    from django.core.serializers.json import DjangoJSONEncoder
    from wagtail.admin.templatetags.wagtailadmin_tags import wagtail_config

    # Le bloc porte le nonce de la réponse. « script-src 'self' » vaut aussi
    # pour les blocs en ligne, y compris de type « application/json » : sans
    # nonce, le navigateur le bloque, « vendor.js » lit une chaîne vide et lève
    # « Unexpected end of JSON input ». L'élément est bien dans le HTML servi —
    # c'est ce qui rend le défaut si difficile à voir depuis le serveur.
    charge = json.dumps(wagtail_config(context), cls=DjangoJSONEncoder).translate(
        {ord("<"): "\u003c", ord(">"): "\u003e", ord("&"): "\u0026"}
    )
    requete = context.get("request")
    nonce = getattr(requete, "csp_nonce", "") if requete is not None else ""
    configuration = format_html(
        '<script id="wagtail-config" type="application/json" nonce="{}">{}</script>',
        nonce,
        mark_safe(charge),  # noqa: S308 — échappé ci-dessus comme le fait « json_script »
    )
    scripts = format_html_join("\n", '<script src="{}"></script>', ((versioned_static(c),) for c in SOCLE))
    return format_html("{}\n{}", configuration, scripts)
