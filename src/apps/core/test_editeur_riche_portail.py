"""Contrat du composant Draftail commun aux espaces privés."""

import json

import pytest
from django.urls import reverse
from wagtail.admin.icons import get_icons

from apps.accounts.models import User
from apps.core.editeur_riche import DraftailPortail
from apps.lms.forms import AnnonceForm
from apps.website.formulaires_actualites import ActualiteForm
from apps.website.formulaires_articles import ArticleForm


def _contentstate(type_bloc="ITEAG_ALIGN_JUSTIFY", texte="Texte structuré"):
    return json.dumps(
        {
            "blocks": [
                {
                    "key": "iteag1",
                    "type": type_bloc,
                    "depth": 0,
                    "text": texte,
                    "inlineStyleRanges": [],
                    "entityRanges": [],
                    "data": {},
                }
            ],
            "entityMap": {},
        }
    )


@pytest.mark.parametrize(
    ("formulaire", "champ"),
    [(ArticleForm, "corps"), (ActualiteForm, "corps"), (AnnonceForm, "contenu")],
)
def test_le_meme_widget_draftail_equipe_les_formulaires_metier(formulaire, champ):
    assert isinstance(formulaire().fields[champ].widget, DraftailPortail)


def test_contentstate_est_converti_en_html_persistable():
    widget = DraftailPortail()
    html = widget.value_from_datadict({"contenu": _contentstate()}, {}, "contenu")

    assert 'class="iteag-align-justify"' in html
    assert html.endswith("Texte structuré</p>")


def test_un_ancien_client_html_reste_compatible():
    widget = DraftailPortail()
    html = '<p class="iteag-align-right">Ancienne intégration</p>'

    assert widget.value_from_datadict({"contenu": html}, {}, "contenu") == html


def test_un_saut_de_ligne_html_heritage_peut_etre_reaffiche():
    widget = DraftailPortail()

    valeur = widget.format_value("<p>Ligne<br>Suite</p>")

    assert '"text": "Ligne\\nSuite"' in valeur


def test_les_ressources_sont_locales_et_chargees_dans_l_ordre():
    media = ArticleForm().media
    ressources = [*media._css.get("all", []), *media._js]

    assert all(not str(ressource).startswith(("http://", "https://")) for ressource in ressources)
    assert "draftail-portail-preparation.js" in media._js[0]
    assert next(i for i, url in enumerate(media._js) if "/vendor.js" in url) < next(
        i for i, url in enumerate(media._js) if "/draftail.js" in url
    )
    assert next(i for i, url in enumerate(media._js) if "/draftail.js" in url) < next(
        i for i, url in enumerate(media._js) if "/draftail-portail.js" in url
    )


def test_les_alignements_utilisent_des_icones_et_non_des_lettres():
    sprite = get_icons()

    for nom in ("left", "center", "right", "justify"):
        assert f'id="icon-align-{nom}"' in sprite


@pytest.mark.django_db
def test_le_dialogue_de_lien_est_prive_mais_accessible_hors_admin(client):
    adresse = reverse("core:editeur_lien_externe")
    assert client.get(adresse).status_code == 302

    utilisateur = User.objects.create_user(
        username="redacteur_draftail",
        email="redacteur-draftail@iteag.test",
        password="test-draftail-2026",
        role=User.Role.ENSEIGNANT,
    )
    client.force_login(utilisateur)
    reponse = client.get(adresse)

    assert reponse.status_code == 200
    assert "external-link-chooser" in reponse.content.decode()
