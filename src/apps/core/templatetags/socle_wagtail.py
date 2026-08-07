"""Socle JavaScript Wagtail nécessaire aux widgets rendus hors de l'admin.

Un ``BlockWidget`` de StreamField n'est pas un champ HTML autonome : Wagtail
rend d'abord un conteneur ``data-controller=\"w-block\"``, puis son runtime
client dépaquette la définition Telepath et construit l'interface. Dans
``wagtailadmin/admin_base.html``, la configuration ``wagtail-config`` est émise
avant ``core.js`` et ``vendor.js``. Un portail Django qui rend un BlockWidget
doit respecter le même contrat avant de charger les médias propres au widget.
"""

from django import template
from django.utils.html import format_html, format_html_join
from django.utils.safestring import mark_safe
from wagtail.admin.staticfiles import versioned_static

register = template.Library()

# Sous-ensemble du socle officiel de wagtailadmin/admin_base.html requis par
# les widgets utilisés dans les portails ITEAG. Les médias spécifiques
# (telepath/blocks.js, Draftail, TypedTableBlock, choosers...) restent déclarés
# par le widget lui-même via ``form.media``.
SOCLE = (
    "wagtailadmin/js/vendor/jquery-3.6.0.min.js",
    "wagtailadmin/js/vendor/bootstrap-transition.js",
    "wagtailadmin/js/vendor/bootstrap-modal.js",
    # core.js crée window.telepath et initialise les contrôleurs Stimulus Wagtail.
    "wagtailadmin/js/core.js",
    # Les bundles StreamField / Draftail partagent les dépendances de vendor.js.
    "wagtailadmin/js/vendor.js",
    "wagtailadmin/js/modal-workflow.js",
)


@register.simple_tag(takes_context=True)
def wagtail_socle_portail(context):
    """Émet la configuration Wagtail puis son runtime de base, dans cet ordre.

    La configuration n'est pas décorative : les bundles Wagtail la lisent au
    démarrage. Elle porte le nonce CSP de la réponse, car un ``script`` de type
    ``application/json`` reste soumis à ``script-src``.
    """
    import json

    from django.core.serializers.json import DjangoJSONEncoder
    from wagtail.admin.templatetags.wagtailadmin_tags import wagtail_config

    charge = json.dumps(wagtail_config(context), cls=DjangoJSONEncoder).translate(
        {ord("<"): "\u003c", ord(">"): "\u003e", ord("&"): "\u0026"}
    )
    requete = context.get("request")
    nonce = getattr(requete, "csp_nonce", "") if requete is not None else ""
    configuration = format_html(
        '<script id="wagtail-config" type="application/json" nonce="{}">{}</script>',
        nonce,
        mark_safe(charge),  # noqa: S308 — caractères HTML sensibles échappés ci-dessus
    )
    scripts = format_html_join("\n", '<script src="{}"></script>', ((versioned_static(c),) for c in SOCLE))
    return format_html("{}\n{}", configuration, scripts)
