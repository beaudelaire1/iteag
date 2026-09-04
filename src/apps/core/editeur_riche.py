"""Éditeurs Wagtail utilisables dans les portails métier de l'ITEAG."""

from __future__ import annotations

import json
import re

from django import forms
from django.core.serializers.json import DjangoJSONEncoder
from django.templatetags.static import static
from django.urls import reverse
from django.utils.functional import cached_property
from wagtail.admin.icons import get_icon_sprite_url
from wagtail.admin.rich_text.editors.draftail import DraftailRichTextArea
from wagtail.admin.staticfiles import versioned_static
from wagtail.blocks import BlockWidget

from apps.core.templatetags.socle_wagtail import SOCLE

# Profil éditorial commun aux articles, actualités et annonces. Les images et
# documents restent des champs structurés dédiés : leurs droits, crédits et
# fichiers ne doivent pas être cachés dans du HTML libre.
FONCTIONNALITES_EDITEUR_PORTAIL = (
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "bold",
    "italic",
    "underline",
    "strikethrough",
    "superscript",
    "subscript",
    "code",
    "ol",
    "ul",
    "blockquote",
    "align-left",
    "align-center",
    "align-right",
    "align-justify",
    "hr",
    "link",
)

VERSION_ASSETS_EDITEUR = "11"


def _asset_iteag(chemin: str) -> str:
    """URL statique ITEAG avec cache-buster propre au composant."""
    return f"{static(chemin)}?v={VERSION_ASSETS_EDITEUR}"


class StreamFieldPortail(BlockWidget):
    """BlockWidget Wagtail avec son runtime de base hors administration.

    Le rendu du widget reste intégralement celui de Wagtail. Cette classe ne
    réimplémente ni Telepath ni le StreamField : elle ajoute seulement les
    bundles que ``wagtailadmin/admin_base.html`` charge normalement avant les
    médias propres aux blocs. Le gabarit doit émettre ``wagtail-config`` avant
    ``form.media.js`` via ``wagtail_configuration_portail``.

    ``core.css`` n'est volontairement pas importé : il contient les resets et
    styles d'éléments globaux de l'administration Wagtail. Le portail fournit
    à la place des feuilles ciblées sur les composants réellement utilisés.
    """

    @cached_property
    def media(self):
        media_blocs = super().media
        prerequis = [versioned_static(chemin) for chemin in SOCLE]
        css = {medium: list(urls) for medium, urls in media_blocs._css.items()}
        css.setdefault("all", []).extend(
            [
                _asset_iteag("css/streamfield-portail.css"),
                _asset_iteag("css/streamfield-draftail-portail.css"),
                _asset_iteag("css/streamfield-picker-portail.css"),
                _asset_iteag("css/typed-table-portail.css"),
                _asset_iteag("css/streamfield-ux-portail.css"),
            ]
        )
        return forms.Media(
            css=css,
            js=[
                *prerequis,
                *media_blocs._js,
                _asset_iteag("js/streamfield-draftail-portail.js"),
                _asset_iteag("js/streamfield-picker-portail.js"),
            ],
        )


class DraftailPortail(DraftailRichTextArea):
    """Draftail utilisable dans un formulaire Django hors du back-office."""

    def __init__(self, *args, libelle="Zone d'édition", placeholder="Rédigez votre contenu…", **kwargs):
        kwargs.setdefault("features", FONCTIONNALITES_EDITEUR_PORTAIL)
        attrs = kwargs.setdefault("attrs", {})
        attrs["data-editeur-draftail-portail"] = True
        super().__init__(*args, **kwargs)
        self.options.update(
            {
                "ariaLabel": libelle,
                "placeholder": placeholder,
                "enableHorizontalRule": True,
            }
        )

    def get_context(self, name, value, attrs):
        # Le sélecteur de lien natif pointe vers l'admin Wagtail, inaccessible
        # aux enseignants. On garde son dialogue officiel, mais sur une route
        # authentifiée du portail qui ne donne accès à aucune donnée d'admin.
        adresse_lien = reverse("core:editeur_lien_externe")
        for entite in self.options.get("entityTypes", []):
            if entite.get("type") == "LINK":
                entite["chooserUrls"] = {
                    "pageChooser": adresse_lien,
                    "externalLinkChooser": adresse_lien,
                    "emailLinkChooser": adresse_lien,
                    "phoneLinkChooser": adresse_lien,
                    "anchorLinkChooser": adresse_lien,
                }

        context = super().get_context(name, value, attrs)
        context["widget"]["attrs"]["data-iteag-icon-url"] = get_icon_sprite_url()
        return context

    def value_from_datadict(self, data, files, name):
        """Accepte ContentState, tout en préservant les intégrations HTML."""
        valeur = data.get(name)
        if valeur in (None, ""):
            return valeur
        try:
            contenu = json.loads(valeur)
        except (TypeError, ValueError):
            return valeur
        if not isinstance(contenu, dict) or "blocks" not in contenu:
            return valeur
        return self.converter.to_database_format(json.dumps(contenu, cls=DjangoJSONEncoder))

    def format_value(self, value):
        """Normalise les sauts de ligne des anciens éditeurs HTML."""
        if isinstance(value, str):
            value = re.sub(r"<br\s*/?>", "<br />", value, flags=re.IGNORECASE)
        return super().format_value(value)

    @cached_property
    def media(self):
        return forms.Media(
            css={
                "all": [
                    versioned_static("wagtailadmin/css/panels/draftail.css"),
                    _asset_iteag("css/draftail-portail.css"),
                    _asset_iteag("css/wagtail-editeur-riche.css"),
                ]
            },
            js=[
                _asset_iteag("js/draftail-portail-preparation.js"),
                versioned_static("wagtailadmin/js/vendor/jquery-3.6.0.min.js"),
                versioned_static("wagtailadmin/js/vendor/bootstrap-transition.js"),
                versioned_static("wagtailadmin/js/vendor/bootstrap-modal.js"),
                versioned_static("wagtailadmin/js/vendor.js"),
                versioned_static("wagtailadmin/js/modal-workflow.js"),
                versioned_static("wagtailadmin/js/draftail.js"),
                versioned_static("wagtailadmin/js/page-chooser-modal.js"),
                _asset_iteag("js/draftail-portail.js"),
            ],
        )


class ChampTexteRiche(forms.CharField):
    """Champ prêt à réutiliser dans tout formulaire des quatre espaces."""

    def __init__(
        self,
        *args,
        label="Contenu",
        placeholder="Rédigez votre contenu…",
        min_height="18rem",
        features=None,
        **kwargs,
    ):
        widget = DraftailPortail(
            features=features or FONCTIONNALITES_EDITEUR_PORTAIL,
            libelle=label,
            placeholder=placeholder,
            attrs={"data-iteag-min-height": min_height},
        )
        super().__init__(*args, label=label, widget=widget, **kwargs)
