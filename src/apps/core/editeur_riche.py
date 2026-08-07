"""Éditeur Draftail partagé par les formulaires métier de l'ITEAG.

Wagtail initialise normalement Draftail depuis son propre tableau de bord. Les
enseignants, étudiants et membres du secrétariat travaillent, eux, dans les
portails Django de l'ITEAG. Ce widget conserve le convertisseur officiel
HTML/ContentState de Wagtail, mais livre une initialisation et une apparence
autonomes, sans CDN et sans charger toute l'interface d'administration.
"""

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

VERSION_ASSETS_EDITEUR = "3"


def _asset_iteag(chemin: str) -> str:
    """URL statique ITEAG avec cache-buster propre au composant."""
    return f"{static(chemin)}?v={VERSION_ASSETS_EDITEUR}"


class StreamFieldPortail(BlockWidget):
    """Widget StreamField utilisable hors de l'administration Wagtail.

    ``BlockWidget.media`` ne déclare que les adaptateurs propres aux blocs :
    Wagtail considère que son ``admin_base.html`` a déjà chargé le runtime
    global (notamment ``core.js``, qui crée ``window.telepath``). Dans les
    portails ITEAG cette hypothèse est fausse. Sans ces prérequis, le conteneur
    ``data-controller=\"w-block\"`` reste vide et aucune zone de saisie n'est
    rendue.

    On fournit ici uniquement les dépendances JavaScript nécessaires au widget
    et à Draftail ; aucune feuille de style ni navigation de l'admin n'est
    injectée dans le portail.
    """

    @cached_property
    def media(self):
        media_blocs = super().media
        prerequis = [
            versioned_static("wagtailadmin/js/vendor/jquery-3.6.0.min.js"),
            versioned_static("wagtailadmin/js/vendor/bootstrap-transition.js"),
            versioned_static("wagtailadmin/js/vendor/bootstrap-modal.js"),
            # core.js instancie window.telepath et le runtime Stimulus Wagtail.
            versioned_static("wagtailadmin/js/core.js"),
            # Draftail est un morceau webpack qui partage ce bundle.
            versioned_static("wagtailadmin/js/vendor.js"),
            versioned_static("wagtailadmin/js/modal-workflow.js"),
            versioned_static("wagtailadmin/js/page-chooser-modal.js"),
        ]
        return forms.Media(css=media_blocs._css, js=[*prerequis, *media_blocs._js])


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
        """Accepte ContentState, tout en préservant les intégrations HTML.

        Le navigateur envoie le JSON ContentState produit par Draftail. Les
        imports, tests et anciens clients peuvent encore envoyer le HTML déjà
        sérialisé ; le reconnaître évite une rupture brutale du contrat HTTP.
        """
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
        """Normalise les sauts de ligne des anciens éditeurs HTML.

        Quill et certains navigateurs ont enregistré ``<br>`` comme une
        balise ouvrante. Le convertisseur Wagtail attend sa forme XHTML
        autofermante ; sans cette adaptation, une ancienne actualité vide ne
        peut même plus être réaffichée après une erreur de validation.
        """
        if isinstance(value, str):
            value = re.sub(r"<br\s*/?>", "<br />", value, flags=re.IGNORECASE)
        return super().format_value(value)

    @cached_property
    def media(self):
        # ``draftail.js`` est un morceau webpack qui partage ses dépendances
        # avec ``vendor.js``. Dans l'admin elles sont déjà présentes ; dans un
        # portail il faut les déclarer explicitement. Les quatre petits scripts
        # jQuery/Bootstrap ne servent qu'au dialogue officiel d'insertion de
        # lien et restent tous auto-hébergés.
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
