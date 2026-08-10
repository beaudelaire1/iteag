import json

import pytest
from django.core.cache import cache
from django.urls import reverse

from apps.elearning import bunny_metadata
from apps.elearning.csp import directives_video
from apps.elearning.models import VideoAsset


class ReponseBunny:
    def __init__(self, charge):
        self.charge = charge

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps(self.charge).encode("utf-8")


def test_chapitres_bunny_sont_normalises_et_mis_en_cache(monkeypatch, settings):
    cache.clear()
    # Ces deux valeurs passent par les réglages Django et non par os.environ :
    # autrement, `verifier_production` ne peut pas contrôler leur présence, et
    # leur absence ne se voit qu'à l'usage — un lecteur sans chapitres.
    settings.BUNNY_STREAM_LIBRARY_ID = "12345"
    settings.BUNNY_STREAM_API_KEY = "cle-api-privee"
    appels = []

    def faux_urlopen(requete, timeout):
        appels.append((requete, timeout))
        return ReponseBunny(
            {
                "chapters": [
                    {"title": "Deuxième partie", "start": 125.4, "end": 300},
                    {"title": "Introduction", "start": 0, "end": 125.4},
                    {"title": "", "start": 10, "end": 20},
                    {"title": "Invalide", "start": 30, "end": 20},
                ]
            }
        )

    monkeypatch.setattr(bunny_metadata, "urlopen", faux_urlopen)

    attendu = [
        {"titre": "Introduction", "debut": 0, "fin": 125},
        {"titre": "Deuxième partie", "debut": 125, "fin": 300},
    ]
    assert bunny_metadata.chapitres_video("video-123") == attendu
    assert bunny_metadata.chapitres_video("video-123") == attendu
    assert len(appels) == 1
    assert appels[0][0].get_header("Accesskey") == "cle-api-privee"


def test_chapitres_bunny_sont_facultatifs_sans_cle_api(settings):
    """La lecture ne dépend jamais de l'API : sans clé, la vidéo démarre quand même."""
    cache.clear()
    settings.BUNNY_STREAM_LIBRARY_ID = ""
    settings.BUNNY_STREAM_API_KEY = ""

    assert bunny_metadata.chapitres_video("video-123") == []


def test_csp_video_autorise_les_sprites_bunny(settings):
    settings.BUNNY_ZONE_DIFFUSION = "https://vz-test.b-cdn.net"

    ajouts, _remplacements = directives_video()

    assert "https://vz-test.b-cdn.net" in ajouts["img-src"]


@pytest.mark.django_db
def test_endpoint_metadata_protege_les_sprites_et_retourne_les_chapitres(
    client,
    utilisateur_etudiant,
    lecon,
    acces,
    settings,
    monkeypatch,
):
    settings.BUNNY_ZONE_DIFFUSION = "https://vz-test.b-cdn.net"
    settings.BUNNY_CLE_SIGNATURE = "signature-super-secrete"
    settings.BUNNY_LIER_ADRESSE_IP = False
    lecon.video.fournisseur = "bunny"
    lecon.video.cle_stockage = "video123456"
    lecon.video.statut_traitement = VideoAsset.StatutTraitement.PRET
    lecon.video.save(update_fields=["fournisseur", "cle_stockage", "statut_traitement"])

    monkeypatch.setattr(
        "apps.elearning.views_bunny.chapitres_video",
        lambda _identifiant: [{"titre": "Introduction", "debut": 0, "fin": 120}],
    )
    client.force_login(utilisateur_etudiant)

    reponse = client.get(
        reverse(
            "elearning:lecon_metadata",
            kwargs={"slug": lecon.chapitre.module.slug, "lecon_slug": lecon.slug},
        )
    )

    assert reponse.status_code == 200
    charge = reponse.json()
    assert charge["chapitres"] == [{"titre": "Introduction", "debut": 0, "fin": 120}]
    assert charge["seek_url_prefix"].startswith("https://vz-test.b-cdn.net/bcdn_token=")
    assert charge["seek_url_prefix"].endswith("/video123456/seek/")
    assert "signature-super-secrete" not in charge["seek_url_prefix"]
    assert charge["intervalle_apercu"] == 2


@pytest.mark.django_db
def test_endpoint_metadata_refuse_un_visiteur_sans_droit(client, lecon, settings):
    settings.BUNNY_ZONE_DIFFUSION = "https://vz-test.b-cdn.net"
    settings.BUNNY_CLE_SIGNATURE = "signature-super-secrete"
    lecon.video.fournisseur = "bunny"
    lecon.video.cle_stockage = "video123456"
    lecon.video.save(update_fields=["fournisseur", "cle_stockage"])

    reponse = client.get(
        reverse(
            "elearning:lecon_metadata",
            kwargs={"slug": lecon.chapitre.module.slug, "lecon_slug": lecon.slug},
        )
    )

    assert reponse.status_code == 403
