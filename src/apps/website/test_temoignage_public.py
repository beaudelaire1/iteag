import pytest
from django.urls import reverse

from apps.website.models_publications import TemoignageEtudiant

pytestmark = pytest.mark.django_db


def _temoignage(**surcharges):
    donnees = {
        "nom_affiche": "Maya Jean",
        "promotion": "Promotion 2026",
        "texte": "<p>Un témoignage <strong>complet</strong> destiné à la lecture publique.</p>",
        "consentement_publication": True,
        "statut": TemoignageEtudiant.Statut.PUBLIE,
    }
    donnees.update(surcharges)
    return TemoignageEtudiant.objects.create(**donnees)


def test_la_page_publique_affiche_le_texte_valide(client):
    temoignage = _temoignage()

    reponse = client.get(reverse("website:temoignage_public", kwargs={"pk": temoignage.pk}))

    assert reponse.status_code == 200
    html = reponse.content.decode()
    assert "Maya Jean" in html
    assert "<strong>complet</strong>" in html
    assert "Retour aux témoignages" in html


@pytest.mark.parametrize(
    ("statut", "consentement"),
    [
        (TemoignageEtudiant.Statut.EN_ATTENTE, True),
        (TemoignageEtudiant.Statut.REFUSE, True),
        (TemoignageEtudiant.Statut.RETIRE, True),
        (TemoignageEtudiant.Statut.PUBLIE, False),
    ],
)
def test_un_temoignage_non_public_reste_introuvable(client, statut, consentement):
    temoignage = _temoignage(statut=statut, consentement_publication=consentement)

    reponse = client.get(reverse("website:temoignage_public", kwargs={"pk": temoignage.pk}))

    assert reponse.status_code == 404
