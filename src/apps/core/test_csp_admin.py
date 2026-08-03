"""La politique de sécurité ne doit se relâcher que là où c'est indispensable.

Le thème de l'administration Django écrit ses scripts dans la page ; sans
dérogation, ses écrans sont muets. La dérogation ne vaut que pour ce préfixe :
si elle débordait sur le site public, une injection de contenu deviendrait
exécutable. Ces deux tests tiennent les deux bouts.
"""

from __future__ import annotations

import pytest

POLITIQUE = {
    "DIRECTIVES": {
        "default-src": ["'self'"],
        "script-src": ["'self'"],
    },
}


@pytest.fixture(autouse=True)
def politique_stricte(settings):
    """Les réglages de test neutralisent la CSP : on la rétablit ici."""
    settings.CONTENT_SECURITY_POLICY = POLITIQUE


@pytest.mark.django_db
class TestLaDerogationResteCantonnee:
    def test_une_page_publique_refuse_le_script_en_ligne(self, client):
        entete = client.get("/connexion/").headers["Content-Security-Policy"]

        assert "script-src 'self'" in entete
        assert "'unsafe-inline'" not in entete

    def test_l_administration_django_tolere_ses_propres_scripts(self, client):
        entete = client.get("/django-admin/").headers["Content-Security-Policy"]

        assert "script-src 'self' 'unsafe-inline'" in entete

    def test_l_administration_django_n_ouvre_pas_pour_autant_les_origines_tierces(self, client):
        entete = client.get("/django-admin/").headers["Content-Security-Policy"]

        assert "default-src 'self'" in entete
        assert "https://" not in entete.split("script-src")[1].split(";")[0]
