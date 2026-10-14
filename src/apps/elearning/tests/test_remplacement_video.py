"""Déposer une vidéo sur une leçon qui en porte déjà une la remplace.

La liste des vidéos arrivait positionnée sur la vidéo actuelle : déposer un
nouveau fichier était refusé (« Une seule vidéo à la fois »), et il fallait
détacher l'ancienne, enregistrer, puis revenir déposer la nouvelle. L'ancienne
restait ensuite dans la bibliothèque sans que rien ne la lise.
"""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.elearning.forms import LeconForm
from apps.elearning.models import Lecon, VideoAsset

pytestmark = pytest.mark.django_db

MP4 = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom" + b"\x00" * 64


@pytest.fixture
def depot_simule(monkeypatch):
    """Le dépôt crée une vidéo prête, sans appeler l'hébergeur."""

    def deposer(self, fichier, titre):
        return VideoAsset.objects.create(
            titre=titre,
            cle_stockage=f"videos/{fichier.name}",
            fournisseur="local",
            duree_secondes=900,
            uploade_par=self.enseignant,
            statut_traitement=VideoAsset.StatutTraitement.PRET,
        )

    monkeypatch.setattr(LeconForm, "_deposer", deposer)


@pytest.fixture
def lecon_de_l_enseignant(lecon, enseignant):
    lecon.video.uploade_par = enseignant.user
    lecon.video.save(update_fields=["uploade_par"])
    return lecon


def saisie(lecon, **extra):
    """Ce que le navigateur envoie : la liste reste positionnée sur la vidéo actuelle."""
    return {
        "titre": lecon.titre,
        "type_lecon": Lecon.TypeLecon.VIDEO,
        "ordre": lecon.ordre,
        "video": lecon.video_id,
        "duree_secondes": 0,
        "obligatoire": "on",
        **extra,
    }


def modifier(client, lecon, donnees):
    return client.post(reverse("elearning:enseignant_lecon_modifier", kwargs={"pk": lecon.pk}), donnees)


def test_un_nouveau_fichier_remplace_et_efface_l_ancienne_video(
    client, enseignant, lecon_de_l_enseignant, depot_simule, django_capture_on_commit_callbacks
):
    ancienne = lecon_de_l_enseignant.video
    client.force_login(enseignant.user)

    with django_capture_on_commit_callbacks(execute=True):
        reponse = modifier(
            client,
            lecon_de_l_enseignant,
            saisie(lecon_de_l_enseignant, video_fichier=SimpleUploadedFile("seance-2.mp4", MP4, "video/mp4")),
        )

    assert reponse.status_code == 302
    lecon_de_l_enseignant.refresh_from_db()
    assert lecon_de_l_enseignant.video.cle_stockage == "videos/seance-2.mp4"
    assert not VideoAsset.objects.filter(pk=ancienne.pk).exists()


def test_une_video_choisie_dans_la_liste_remplace_aussi_l_ancienne(
    client, enseignant, lecon_de_l_enseignant, django_capture_on_commit_callbacks
):
    ancienne = lecon_de_l_enseignant.video
    nouvelle = VideoAsset.objects.create(
        titre="Séance 2",
        cle_stockage="videos/seance-2-bis.mp4",
        fournisseur="local",
        uploade_par=enseignant.user,
        statut_traitement=VideoAsset.StatutTraitement.PRET,
    )
    client.force_login(enseignant.user)

    with django_capture_on_commit_callbacks(execute=True):
        modifier(client, lecon_de_l_enseignant, saisie(lecon_de_l_enseignant, video=nouvelle.pk))

    lecon_de_l_enseignant.refresh_from_db()
    assert lecon_de_l_enseignant.video == nouvelle
    assert not VideoAsset.objects.filter(pk=ancienne.pk).exists()


def test_une_video_encore_utilisee_ailleurs_est_conservee(
    client, enseignant, chapitre, lecon_de_l_enseignant, depot_simule, django_capture_on_commit_callbacks
):
    ancienne = lecon_de_l_enseignant.video
    Lecon.objects.create(
        chapitre=chapitre, titre="Reprise", slug="reprise", type_lecon=Lecon.TypeLecon.VIDEO, video=ancienne, ordre=2
    )
    client.force_login(enseignant.user)

    with django_capture_on_commit_callbacks(execute=True):
        modifier(
            client,
            lecon_de_l_enseignant,
            saisie(lecon_de_l_enseignant, video_fichier=SimpleUploadedFile("seance-2.mp4", MP4, "video/mp4")),
        )

    lecon_de_l_enseignant.refresh_from_db()
    assert lecon_de_l_enseignant.video != ancienne
    assert VideoAsset.objects.filter(pk=ancienne.pk).exists()


def test_corriger_le_titre_garde_la_video(
    client, enseignant, lecon_de_l_enseignant, django_capture_on_commit_callbacks
):
    video = lecon_de_l_enseignant.video
    client.force_login(enseignant.user)

    with django_capture_on_commit_callbacks(execute=True):
        reponse = modifier(client, lecon_de_l_enseignant, saisie(lecon_de_l_enseignant, titre="Le Christ, vrai homme"))

    assert reponse.status_code == 302
    lecon_de_l_enseignant.refresh_from_db()
    assert lecon_de_l_enseignant.titre == "Le Christ, vrai homme"
    assert lecon_de_l_enseignant.video == video


def test_le_secretariat_corrige_la_lecon_d_un_enseignant_sans_perdre_sa_video(
    client, secretaire, lecon_de_l_enseignant, django_capture_on_commit_callbacks
):
    """La vidéo déposée par l'enseignant doit figurer dans la liste du secrétariat."""
    video = lecon_de_l_enseignant.video
    client.force_login(secretaire)

    with django_capture_on_commit_callbacks(execute=True):
        reponse = modifier(client, lecon_de_l_enseignant, saisie(lecon_de_l_enseignant, titre="Titre corrigé"))

    assert reponse.status_code == 302
    lecon_de_l_enseignant.refresh_from_db()
    assert lecon_de_l_enseignant.titre == "Titre corrigé"
    assert lecon_de_l_enseignant.video == video


def test_l_ecran_annonce_le_remplacement(client, enseignant, lecon_de_l_enseignant):
    client.force_login(enseignant.user)

    reponse = client.get(reverse("elearning:enseignant_lecon_modifier", kwargs={"pk": lecon_de_l_enseignant.pk}))

    contenu = reponse.content.decode()
    assert "Vidéo actuelle" in contenu
    assert "Un nouveau fichier la remplace" in contenu
