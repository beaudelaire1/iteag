"""
La commande de vérification Bunny, éprouvée sans toucher au réseau.

Elle est l'outil qu'on saisit un jour d'incident, souvent dans l'urgence et
souvent sans l'avoir jamais lancée. Ce qu'il faut donc garantir : qu'elle
refuse proprement une configuration incomplète, qu'elle dise ce qu'elle a
trouvé, et surtout qu'elle **ne divulgue jamais la clé de signature** — un
diagnostic se copie dans un ticket ou se colle dans une conversation.
"""

from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

CLE = "cle-de-signature-tres-secrete-0123456789"
ZONE = "https://vz-test.b-cdn.net"

MANIFESTE = "#EXTM3U\n#EXT-X-VERSION:3\n#EXTINF:6.0,\nsegment-0.ts\n"


@pytest.fixture(autouse=True)
def _config(settings):
    settings.BUNNY_ZONE_DIFFUSION = ZONE
    settings.BUNNY_CLE_SIGNATURE = CLE
    settings.BUNNY_LIER_ADRESSE_IP = False


def lancer(*args, **options) -> str:
    sortie = StringIO()
    call_command("verifier_bunny", *args, stdout=sortie, **options)
    return sortie.getvalue()


class TestConfigurationIncomplete:
    def test_sans_zone_la_commande_refuse_et_explique(self, settings):
        settings.BUNNY_ZONE_DIFFUSION = ""
        with pytest.raises(CommandError) as echec:
            lancer("abc")
        assert "BUNNY_ZONE_DIFFUSION" in str(echec.value)

    def test_sans_cle_la_commande_refuse(self, settings):
        settings.BUNNY_CLE_SIGNATURE = ""
        with pytest.raises(CommandError):
            lancer("abc")


class TestCeQueLaCommandeRapporte:
    def test_le_cas_nominal_conclut_au_succes(self):
        with patch(
            "apps.elearning.management.commands.verifier_bunny._statut",
            return_value=(200, MANIFESTE),
        ):
            sortie = lancer("abc123")
        assert "200" in sortie
        assert "la lecture protégée fonctionne" in sortie

    def test_un_segment_refuse_est_dit_explicitement(self):
        """
        Le cas qui compte : le manifeste passe, le segment non. C'est le
        symptôme d'une signature de fichier au lieu d'une signature de
        répertoire, et il ne se voit pas en regardant seulement la première
        requête.
        """
        reponses = iter([(200, MANIFESTE), (403, "")])

        with patch(
            "apps.elearning.management.commands.verifier_bunny._statut",
            side_effect=lambda url: next(reponses),
        ):
            sortie = lancer("abc123")
        assert "Le manifeste passe mais pas le segment" in sortie

    def test_un_manifeste_refuse_declenche_le_diagnostic(self):
        with patch(
            "apps.elearning.management.commands.verifier_bunny._statut",
            return_value=(403, ""),
        ):
            sortie = lancer("abc123")
        assert "configuration Bunny" in sortie
        assert "HMAC-SHA256" in sortie

    def test_le_diagnostic_detecte_une_zone_non_protegee(self):
        reponses = iter([(403, ""), (200, "")])

        with patch(
            "apps.elearning.management.commands.verifier_bunny._statut",
            side_effect=lambda url: next(reponses),
        ):
            sortie = lancer("abc123")
        assert "Le manifeste est public" in sortie

    def test_une_zone_injoignable_ne_fait_pas_planter(self):
        with patch(
            "apps.elearning.management.commands.verifier_bunny._statut",
            return_value=(0, "nom de domaine introuvable"),
        ):
            sortie = lancer("abc123")
        assert "Injoignable" in sortie


class TestLaCleNeSortJamais:
    """Un diagnostic se colle dans un ticket : il ne doit rien porter de secret."""

    def test_ni_dans_le_cas_nominal(self):
        with patch(
            "apps.elearning.management.commands.verifier_bunny._statut",
            return_value=(200, MANIFESTE),
        ):
            sortie = lancer("abc123")
        assert CLE not in sortie
        assert "renseignée" in sortie

    def test_ni_dans_le_diagnostic_d_echec(self):
        with patch(
            "apps.elearning.management.commands.verifier_bunny._statut",
            return_value=(403, ""),
        ):
            sortie = lancer("abc123")
        assert CLE not in sortie


class TestLAdresseEprouvee:
    def test_le_repertoire_est_signe_et_declare(self):
        vues = []

        with patch(
            "apps.elearning.management.commands.verifier_bunny._statut",
            side_effect=lambda url: (vues.append(url), (200, MANIFESTE))[1],
        ):
            lancer("abc123")

        assert vues[0].startswith(f"{ZONE}/bcdn_token=HS256-")
        assert "token_path=%2Fabc123%2F" in vues[0], "Sans token_path, les segments seraient refusés"
        assert vues[0].endswith("/abc123/playlist.m3u8")

    def test_le_segment_est_demande_avec_la_meme_requete(self):
        vues = []

        with patch(
            "apps.elearning.management.commands.verifier_bunny._statut",
            side_effect=lambda url: (vues.append(url), (200, MANIFESTE))[1],
        ):
            lancer("abc123")

        segments = [url for url in vues if "segment-0.ts" in url]
        assert segments, "Le segment référencé par le manifeste doit être éprouvé"
        assert any("/bcdn_token=HS256-" in url for url in segments)
