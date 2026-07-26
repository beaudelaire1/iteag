"""
Une page publique ne doit pas resservir l'en-tête d'un autre visiteur.

« ParcoursListView » et « ProfesseurListView » étaient enveloppées dans
« cache_page ». Le gabarit qu'elles rendent contient la barre de navigation,
qui n'est pas la même pour tout le monde : elle porte le prénom de qui est
connecté, ses initiales, son rôle et les liens de son espace.

Le cache de page mémorise le HTML complet sous une clé qui ignore la session.
La première version rendue était donc servie à tous les suivants — le prénom et
le rôle d'un étudiant à un visiteur anonyme, ou l'inverse : un connecté se
voyait déconnecté, sans lien vers son espace, sur une page qu'il venait
d'ouvrir.

En production le cache est partagé par tous les processus : la fuite ne se
limite pas à un travailleur.
"""

import pytest
from django.urls import reverse

from apps.accounts.models import User
from apps.formations.models import Professeur


@pytest.fixture
def etudiante(db):
    return User.objects.create_user(
        username="cmartin",
        email="cmartin@iteag.org",
        password="motdepasse-long-12",
        first_name="Claire",
        last_name="Martin",
        role=User.Role.ETUDIANT,
    )


@pytest.fixture
def _professeur(db):
    return Professeur.objects.create(nom="Test", prenom="Prof", slug="prof-cache", actif=True)


@pytest.mark.django_db
@pytest.mark.parametrize("nom_route", ["formations:parcours_list", "formations:professeur_list"])
class TestAucunePageNeFuitEntreVisiteurs:
    def test_le_visiteur_anonyme_ne_recoit_pas_l_en_tete_d_un_connecte(
        self, client, django_user_model, etudiante, _professeur, nom_route
    ):
        chemin = reverse(nom_route)
        client.force_login(etudiante)
        assert "Claire" in client.get(chemin).content.decode(), "L'en-tête connecté n'a pas été rendu"

        client.logout()
        contenu = client.get(chemin).content.decode()
        assert "Claire" not in contenu, "Le prénom d'un connecté est servi à un visiteur anonyme"

    def test_le_connecte_ne_recoit_pas_l_en_tete_anonyme(self, client, etudiante, _professeur, nom_route):
        chemin = reverse(nom_route)
        client.get(chemin)  # un anonyme passe en premier

        client.force_login(etudiante)
        contenu = client.get(chemin).content.decode()
        assert "Claire" in contenu, "Le connecté reçoit la page d'un anonyme — il se croit déconnecté"
