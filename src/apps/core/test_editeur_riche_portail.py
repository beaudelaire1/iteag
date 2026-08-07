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
from apps.website.models_publications import ContenuActualite


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
    [(ArticleForm, "corps"), (AnnonceForm, "contenu")],
)
def test_le_meme_widget_draftail_equipe_les_champs_riches_directs(formulaire, champ):
    assert isinstance(formulaire().fields[champ].widget, DraftailPortail)


def test_actualite_remplace_le_corps_direct_par_un_streamfield_structure():
    formulaire = ActualiteForm()
    assert formulaire.fields["corps"].widget.is_hidden
    assert not formulaire.fields["contenu"].widget.is_hidden
    stream_block = ContenuActualite._meta.get_field("contenu").stream_block
    assert "texte" in stream_block.child_blocks


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


# ══════════════════════════════════════════════
# Le repli, et ce qu'il n'a pas le droit de faire
# ══════════════════════════════════════════════


def _script_amorcage() -> str:
    from pathlib import Path

    from django.conf import settings

    return (Path(settings.BASE_DIR) / "static" / "js" / "draftail-portail.js").read_text(encoding="utf-8")


def _code_seul() -> str:
    """Le script sans ses commentaires.

    Un test qui lit le fichier brut se fait piéger par les commentaires : celui
    qui interdit « bloc.text » trouvait l'expression dans la note expliquant
    pourquoi elle est interdite, et échouait sur sa propre documentation.
    """
    import re

    sans_blocs = re.sub(r"/\*.*?\*/", "", _script_amorcage(), flags=re.S)
    return re.sub(r"^\s*//.*$", "", sans_blocs, flags=re.M)


class TestRepliDeLEditeur:
    """Le défaut qui faisait dire « les boutons sont là mais rien ne marche ».

    L'amorçage repliait l'éditeur sur un « textarea » si « .Draftail-Editor »
    n'était pas peint au bout de 750 ms. Or Draftail a 739 Ko de script à
    analyser avant de peindre : sur une machine chargée, le repli se
    déclenchait sur un éditeur parfaitement fonctionnel, qui apparaissait
    ensuite par-dessus un champ désactivé. La barre d'outils restait visible et
    ne commandait plus rien.

    Pire : le repli aplatissait le contenu à « bloc.text ». Ouvrir un document
    formaté sur un chargement lent puis enregistrer suffisait à en détruire la
    mise en forme, sans le moindre avertissement.
    """

    def test_l_apparition_de_l_editeur_est_observee_et_non_chronometree(self):
        assert "MutationObserver" in _code_seul(), (
            "L'amorçage doit observer l'apparition de l'éditeur. Un délai fixe est une course "
            "que Draftail perd dès que la machine est chargée."
        )

    def test_aucun_repli_sous_cinq_secondes(self):
        """750 ms était plus court que le temps d'analyse du script lui-même."""
        import re

        # « }, 10000) » : le délai est le dernier argument, après la fonction.
        # Une expression qui s'arrête à la première virgule ne franchit pas le
        # corps de la fonction fléchée et ne trouve jamais rien.
        delais = [int(v) for v in re.findall(r"\}\s*,\s*(\d+)\s*\)", _code_seul())]
        assert delais, "Un filet de sécurité reste attendu."
        assert min(delais) >= 5000, f"Repli trop hâtif : {min(delais)} ms."

    def test_le_repli_ne_deforme_pas_le_contenu(self):
        """« bloc.text » jette gras, titres et alignements sans rien dire."""
        assert "bloc.text" not in _code_seul(), (
            "Le repli ne doit pas reconstruire le contenu à partir du seul texte des blocs : "
            "il détruirait la mise en forme de ce qui était déjà enregistré."
        )

    def test_le_repli_retire_la_barre_d_outils(self):
        """Des commandes qui ne commandent rien sont pires qu'aucune commande."""
        assert "Draftail-Toolbar" in _code_seul()

    def test_le_repli_se_signale(self):
        assert 'role", "alert"' in _code_seul(), (
            "Un éditeur dégradé qui se tait laisse conclure à une panne de formatage."
        )
