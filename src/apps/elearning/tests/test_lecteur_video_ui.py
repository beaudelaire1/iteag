from pathlib import Path

import pytest
from django.conf import settings
from django.urls import reverse


def url_lecon(lecon):
    return reverse(
        "elearning:lecon_detail",
        kwargs={"slug": lecon.chapitre.module.slug, "lecon_slug": lecon.slug},
    )


@pytest.mark.django_db
def test_lecteur_affiche_sauts_et_qualite(client, utilisateur_etudiant, lecon, acces):
    client.force_login(utilisateur_etudiant)
    contenu = client.get(url_lecon(lecon)).content.decode("utf-8")

    assert 'data-saut-video="-10"' in contenu
    assert 'data-saut-video="10"' in contenu
    assert "Reculer de 10 secondes" in contenu
    assert "Avancer de 10 secondes" in contenu
    assert "data-qualite-video" in contenu
    assert "data-qualite-active" in contenu


def test_script_pilote_les_resolutions_hls_et_la_preference():
    script = (Path(settings.BASE_DIR) / "static" / "js" / "lecteur-video.js").read_text(encoding="utf-8")

    assert "Hls.Events.MANIFEST_PARSED" in script
    assert "Hls.Events.LEVEL_SWITCHED" in script
    assert "hls.currentLevel = -1" in script
    assert "hls.currentLevel = index" in script
    assert "iteag_video_quality" in script
    assert 'ITEAGConsent?.allows("preferences")' in script
    assert "dataSautVideo" in script
    assert "video.currentTime = cible" in script


def test_qualite_n_est_pas_memorisee_sans_preference_facultative():
    script = (Path(settings.BASE_DIR) / "static" / "js" / "lecteur-video.js").read_text(encoding="utf-8")

    assert "if (!preferencesAutorisees())" in script
    assert "supprimerPreferenceQualite();" in script
