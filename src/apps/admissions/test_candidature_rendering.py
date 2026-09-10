"""Non-régressions du rendu public de la candidature."""

import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_honeypot_est_present_sans_libelle_visible(client):
    reponse = client.get(reverse("admissions:candidature_form"))

    assert reponse.status_code == 200
    html = reponse.content.decode()
    assert 'name="honeypot"' in html
    assert 'type="hidden"' in html
    assert 'for="id_honeypot"' not in html


@pytest.mark.django_db
def test_le_formulaire_est_regroupe_et_annonce_ses_champs_obligatoires(client):
    """Une seule colonne de quinze champs ne dit ni où l'on en est, ni ce qui est dû."""
    html = client.get(reverse("admissions:candidature_form")).content.decode()

    for titre in ("Votre identité", "Votre projet", "Vos pièces justificatives"):
        assert titre in html, titre
    assert html.count("<fieldset") == 3
    assert "Champ obligatoire" in html


@pytest.mark.django_db
def test_le_choix_du_parcours_porte_un_intitule(client):
    """« --------- » n'indique ni qu'un choix est attendu, ni ce qu'on choisit."""
    html = client.get(reverse("admissions:candidature_form")).content.decode()

    assert "Choisissez un parcours" in html
    assert "---------" not in html


@pytest.mark.django_db
def test_chaque_piece_annonce_son_format_et_son_poids(client):
    """Le contrat de dépôt se lisait en essuyant une erreur."""
    html = client.get(reverse("admissions:candidature_form")).content.decode()

    assert html.count("Formats acceptés : PDF, JPEG, PNG, Word ou OpenDocument.") == 3
    assert html.count("10 Mo maximum.") == 3


@pytest.mark.django_db
def test_les_champs_fichier_sont_habillables_en_francais(client):
    """Le bouton natif s'affiche dans la langue du navigateur, pas celle du site.

    Le gabarit pose l'enveloppe et la page charge le script ; sans lui, le
    champ natif reste en place et reste utilisable.
    """
    html = client.get(reverse("admissions:candidature_form")).content.decode()

    assert html.count("data-champ-fichier") == 3
    assert "js/champs-fichier" in html
