"""Configuration et socle Wagtail pour les widgets rendus hors de l'admin.

Un ``BlockWidget`` StreamField n'embarque que ses médias spécifiques. Dans
l'administration, le gabarit Wagtail lui fournit auparavant la configuration,
le runtime de base et le sprite SVG utilisé par ses contrôles. Les portails
ITEAG doivent fournir le même contrat sans importer toute l'interface admin.
"""

from django import template
from django.utils.html import format_html, format_html_join
from django.utils.safestring import mark_safe
from wagtail.admin.icons import get_icon_sprite_url
from wagtail.admin.staticfiles import versioned_static

register = template.Library()

# Sous-ensemble du socle officiel de wagtailadmin/admin_base.html requis par
# les blocs présents dans les publications ITEAG. Les deux bibliothèques de
# calendrier précèdent date-time-chooser.js, que DateBlock peut ajouter via le
# Media du BlockWidget (notamment dans les tableaux typés).
SOCLE = (
    "wagtailadmin/js/vendor/jquery-3.6.0.min.js",
    "wagtailadmin/js/vendor/jquery-ui-1.13.2.min.js",
    "wagtailadmin/js/vendor/jquery.datetimepicker.js",
    "wagtailadmin/js/vendor/bootstrap-transition.js",
    "wagtailadmin/js/vendor/bootstrap-modal.js",
    "wagtailadmin/js/core.js",
    "wagtailadmin/js/vendor.js",
    "wagtailadmin/js/modal-workflow.js",
)


def _configuration_wagtail(context):
    """Construit le ``wagtail-config`` officiel avec le nonce CSP courant."""
    import json

    from django.core.serializers.json import DjangoJSONEncoder
    from wagtail.admin.templatetags.wagtailadmin_tags import wagtail_config

    charge = json.dumps(wagtail_config(context), cls=DjangoJSONEncoder).translate(
        {ord("<"): "\u003c", ord(">"): "\u003e", ord("&"): "\u0026"}
    )
    requete = context.get("request")
    nonce = getattr(requete, "csp_nonce", "") if requete is not None else ""
    return format_html(
        '<script id="wagtail-config" type="application/json" nonce="{}">{}</script>',
        nonce,
        mark_safe(charge),  # noqa: S308 — caractères HTML sensibles échappés ci-dessus
    )


@register.simple_tag(takes_context=True)
def wagtail_configuration_portail(context):
    """Émet uniquement la configuration requise avant les médias du widget."""
    return _configuration_wagtail(context)


@register.simple_tag
def wagtail_icones_portail():
    """Charge le sprite SVG utilisé par les boutons et menus StreamField.

    Un StreamField vide affiche d'abord un bouton dont le SVG référence
    ``#icon-plus``. Sans le sprite chargé par ``skeleton.html`` dans l'admin,
    ce contrôle perd son glyphe dans un portail personnalisé.
    """
    return format_html(
        '<div data-sprite aria-hidden="true"></div><script src="{}" data-icon-url="{}"></script>',
        versioned_static("wagtailadmin/js/icons.js"),
        get_icon_sprite_url(),
    )


@register.simple_tag(takes_context=True)
def wagtail_socle_portail(context):
    """Émet la configuration puis le runtime de base, comme ``admin_base``."""
    configuration = _configuration_wagtail(context)
    scripts = format_html_join("\n", '<script src="{}"></script>', ((versioned_static(c),) for c in SOCLE))
    return format_html("{}\n{}", configuration, scripts)
