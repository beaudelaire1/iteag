"""
Se connecter sans se perdre : avertir avant le blocage, expliquer le blocage,
ne pas couper la session de quelqu'un qui travaille.

La politique elle-même reste celle du cahier des charges (ETU-001) : cinq
essais, trente minutes de blocage, trente minutes d'inactivité.
"""

import pytest
from django.urls import reverse

from apps.accounts.models import User

pytestmark = pytest.mark.django_db

MOT_DE_PASSE = "MotDePasseSolide!2026"


@pytest.fixture
def compte(db):
    return User.objects.create_user(username="marthe", email="marthe@example.org", password=MOT_DE_PASSE)


class TestMaintienDeSession:
    def test_prolonger_repond_sans_contenu(self, client, compte):
        client.force_login(compte)
        assert client.post(reverse("accounts:session_active")).status_code == 204

    def test_une_session_expiree_n_est_pas_prolongee(self, client):
        reponse = client.post(reverse("accounts:session_active"))
        assert reponse.status_code == 302
        assert reverse("accounts:login") in reponse.url

    def test_les_espaces_prives_annoncent_la_duree_reelle(self, client, compte, settings):
        client.force_login(compte)
        page = client.get(reverse("accounts:profil")).content.decode()
        assert f'data-duree="{settings.SESSION_COOKIE_AGE}"' in page
        assert "session-active.js" in page


class TestVerrouillage:
    @pytest.fixture(autouse=True)
    def _verrouillage_actif(self, settings):
        # Désactivé pour le reste de la suite : chaque test ici le rallume.
        settings.AXES_ENABLED = True
        settings.AXES_FAILURE_LIMIT = 5

    def _echouer(self, client, fois):
        reponse = None
        for _ in range(fois):
            reponse = client.post(reverse("accounts:login"), {"username": "marthe", "password": "mauvais"})
        return reponse

    def test_pas_d_avertissement_aux_premiers_essais(self, client, compte):
        reponse = self._echouer(client, 1)
        assert "avant que le compte" not in reponse.content.decode()

    def test_l_avertissement_arrive_avant_le_blocage(self, client, compte):
        reponse = self._echouer(client, 3)
        assert "encore 2 essais avant que le compte" in reponse.content.decode()

    def test_le_blocage_explique_la_duree_et_l_issue(self, client, compte):
        reponse = self._echouer(client, 5)
        assert reponse.status_code == 429
        contenu = reponse.content.decode()
        assert "30 minutes" in contenu
        assert reverse("accounts:password_reset") in contenu
        # La page garde la charte : ce n'est plus une ligne de texte brut.
        assert "<!DOCTYPE html>" in contenu
