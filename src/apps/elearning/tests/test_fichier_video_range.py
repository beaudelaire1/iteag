import pytest
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.urls import reverse


def url_lecture(lecon):
    return reverse(
        "elearning:lecon_playback",
        kwargs={"slug": lecon.chapitre.module.slug, "lecon_slug": lecon.slug},
    )


@pytest.fixture
def adresse_video_locale(client, utilisateur_etudiant, lecon, acces, tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    default_storage.save(lecon.video.cle_stockage, ContentFile(b"contenu-video"))
    client.force_login(utilisateur_etudiant)
    return client.post(url_lecture(lecon)).json()["url"]


@pytest.mark.django_db
def test_range_retourne_uniquement_les_octets_demandes(client, adresse_video_locale):
    reponse = client.get(adresse_video_locale, HTTP_RANGE="bytes=2-5")

    assert reponse.status_code == 206
    assert reponse["Content-Range"] == "bytes 2-5/13"
    assert reponse["Content-Length"] == "4"
    assert reponse["Accept-Ranges"] == "bytes"
    assert b"".join(reponse.streaming_content) == b"nten"


@pytest.mark.django_db
def test_range_ouverte_va_jusqu_a_la_fin(client, adresse_video_locale):
    reponse = client.get(adresse_video_locale, HTTP_RANGE="bytes=8-")

    assert reponse.status_code == 206
    assert reponse["Content-Range"] == "bytes 8-12/13"
    assert b"".join(reponse.streaming_content) == b"video"


@pytest.mark.django_db
def test_range_suffixe_retourne_la_fin(client, adresse_video_locale):
    reponse = client.get(adresse_video_locale, HTTP_RANGE="bytes=-5")

    assert reponse.status_code == 206
    assert reponse["Content-Range"] == "bytes 8-12/13"
    assert b"".join(reponse.streaming_content) == b"video"


@pytest.mark.django_db
def test_range_hors_fichier_est_refusee(client, adresse_video_locale):
    reponse = client.get(adresse_video_locale, HTTP_RANGE="bytes=99-120")

    assert reponse.status_code == 416
    assert reponse["Content-Range"] == "bytes */13"
    assert reponse["Accept-Ranges"] == "bytes"
