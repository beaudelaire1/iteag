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
def test_lecteur_affiche_une_interface_iteag_complete(client, utilisateur_etudiant, lecon, acces):
    client.force_login(utilisateur_etudiant)
    contenu = client.get(url_lecon(lecon)).content.decode("utf-8")

    assert 'controlslist="nodownload"' in contenu
    assert "<video data-video preload=" in contenu
    assert "<video data-video controls " not in contenu
    assert 'data-saut-video="-10"' in contenu
    assert 'data-saut-video="10"' in contenu
    assert "data-video-toggle-play" in contenu
    assert "data-video-timeline" in contenu
    assert "data-video-volume" in contenu
    assert "data-vitesse-video" in contenu
    assert "data-sous-titres-video" in contenu
    assert "data-qualite-video" in contenu
    assert "data-video-pip" in contenu
    assert "data-video-fullscreen" in contenu
    assert "data-video-loading" in contenu
    assert "data-video-end" in contenu
    assert "css/lecteur-video.css" in contenu


def test_script_pilote_les_resolutions_hls_et_la_preference():
    script = (Path(settings.BASE_DIR) / "static" / "js" / "lecteur-video.js").read_text(encoding="utf-8")

    assert "Hls.Events.MANIFEST_PARSED" in script
    assert "Hls.Events.LEVEL_SWITCHED" in script
    assert "hls.currentLevel = -1" in script
    assert "hls.currentLevel = index" in script
    assert "iteag_video_quality" in script
    assert 'ITEAGConsent?.allows("preferences")' in script


def test_script_pilote_navigation_vitesse_sous_titres_et_modes_ecran():
    script = (Path(settings.BASE_DIR) / "static" / "js" / "lecteur-video.js").read_text(encoding="utf-8")

    assert "video.playbackRate" in script
    assert "video.textTracks" in script
    assert "requestPictureInPicture" in script
    assert "requestFullscreen" in script
    assert 'touche === "arrowleft"' in script
    assert 'touche === "arrowright"' in script
    assert 'touche === "m"' in script
    assert 'touche === "f"' in script
    assert "data-reprise-action" in script
    assert "trouverLeconSuivante" in script
    assert "afficherChargement" in script
    assert "video.currentTime" in script


def test_progression_tient_compte_de_la_vitesse_de_lecture():
    script = (Path(settings.BASE_DIR) / "static" / "js" / "lecteur-video.js").read_text(encoding="utf-8")

    assert "ecoule * Math.max(0.25, video.playbackRate || 1)" in script


def test_qualite_n_est_pas_memorisee_sans_preference_facultative():
    script = (Path(settings.BASE_DIR) / "static" / "js" / "lecteur-video.js").read_text(encoding="utf-8")

    assert "if (!preferencesAutorisees())" in script
    assert "supprimerPreferenceQualite();" in script
