"""Configuration et socle Wagtail pour les widgets rendus hors de l'admin.

Les widgets Wagtail dynamiques lisent ``wagtail-config`` avant leur démarrage.
Leur ``Media`` sait ensuite déclarer les scripts propres au widget, mais Django
``forms.Media`` ne peut pas émettre ce bloc JSON inline. Ce module fournit donc
la configuration avec le nonce CSP ; le tag de socle complet reste disponible
pour les écrans qui en auraient besoin.
"""

from django import template
from django.utils.html import format_html, format_html_join
from django.utils.safestring import mark_safe
from wagtail.admin.staticfiles import versioned_static

register = template.Library()

# Sous-ensemble du socle officiel de wagtailadmin/admin_base.html. L'ordre est
# intentionnel : core.js crée window.telepath et l'application Stimulus avant
# que les adaptateurs spécifiques des widgets ne s'enregistrent.
SOCLE = (
    "wagtailadmin/js/vendor/jquery-3.6.0.min.js",
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


@register.simple_tag(takes_context=True)
def wagtail_socle_portail(context):
    """Émet la configuration puis le runtime de base, comme ``admin_base``."""
    configuration = _configuration_wagtail(context)
    scripts = format_html_join("\n", '<script src="{}"></script>', ((versioned_static(c),) for c in SOCLE))
    return format_html("{}\n{}", configuration, scripts)
