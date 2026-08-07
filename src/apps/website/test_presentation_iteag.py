from apps.website.management.commands.setup_initial_pages import PRESENTATION_META, contenu_presentation_initial
from apps.website.models import ContentPage


def test_le_contenu_officiel_est_valide_pour_le_streamfield():
    stream_block = ContentPage._meta.get_field("body").stream_block
    contenu = stream_block.to_python(contenu_presentation_initial())

    assert len(contenu) == 5
    assert [bloc.block_type for bloc in contenu] == ["texte", "texte", "encadre", "texte", "texte"]


def test_la_presentation_reste_factuelle_et_couvre_les_elements_institutionnels():
    brut = repr(contenu_presentation_initial())

    for attendu in (
        "centre de formation",
        "théologie évangélique",
        "association loi 1905",
        "projet fédérateur",
        "formation dispensée localement",
        "équipe pédagogique",
        "théorique et pratique",
        "bibliothèque",
    ):
        assert attendu in brut

    assert "accrédit" not in brut.lower()
    assert "universit" not in brut.lower()
    assert PRESENTATION_META
