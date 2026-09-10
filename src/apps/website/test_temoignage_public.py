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


class TestRepriseDeLAncienSite:
    """Les deux témoignages du carrousel « Ils l'ont vécu » ont survécu à la refonte.

    Ils étaient figés dans le paquet JavaScript de l'ancien site ; la migration
    0018 les remet en base. Le contrôle porte sur ce que voit le public, pas sur
    la migration elle-même : c'est la page qui compte.
    """

    NOMS = {"Eliane Kancel", "Frédéric Jean-Louis"}

    def test_les_deux_temoignages_repris_sont_en_base_et_publics(self):
        repris = TemoignageEtudiant.objects.filter(nom_affiche__in=self.NOMS)

        assert {t.nom_affiche for t in repris} == self.NOMS
        for temoignage in repris:
            assert temoignage.est_public, temoignage.nom_affiche
            assert temoignage.etudiant is None, "Ces auteurs n'ont pas de compte étudiant"
            assert temoignage.promotion, temoignage.nom_affiche

    def test_chaque_temoignage_repris_a_sa_page_publique(self, client):
        for temoignage in TemoignageEtudiant.objects.filter(nom_affiche__in=self.NOMS):
            reponse = client.get(reverse("website:temoignage_public", kwargs={"pk": temoignage.pk}))

            assert reponse.status_code == 200, temoignage.nom_affiche
            assert temoignage.nom_affiche in reponse.content.decode()
