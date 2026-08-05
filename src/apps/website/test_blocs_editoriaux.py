from apps.website.models import FONCTIONNALITES_TEXTE, ContentPage, HomePage, TexteEditorialBlock


def test_le_texte_streamfield_utilise_le_profil_draftail_iteag():
    bloc = TexteEditorialBlock()

    assert bloc.features == FONCTIONNALITES_TEXTE
    assert {"align-left", "align-center", "align-right", "align-justify", "underline"} <= set(bloc.features)
    assert "image" not in bloc.features
    assert "document-link" not in bloc.features


def test_les_pages_streamfield_proposent_des_blocs_structurels():
    attendus = {"texte", "image", "citation", "encadre", "document"}

    assert attendus <= set(HomePage._meta.get_field("body").stream_block.child_blocks)
    assert attendus <= set(ContentPage._meta.get_field("body").stream_block.child_blocks)
