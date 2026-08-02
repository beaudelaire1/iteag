"""Une vidéo référencée doit pouvoir être corrigée, pas seulement supprimée.

Le référencement ne se faisait qu'une fois : un titre mal orthographié, une
durée oubliée ou un lien remplacé chez le fournisseur obligeaient à supprimer
la vidéo — donc à la détacher de ses leçons — puis à tout reconstituer.
"""

import pytest
from django.urls import reverse

from apps.accounts.models import User
from apps.elearning.models import VideoAsset
from apps.formations.models import Professeur

pytestmark = pytest.mark.django_db

MOT_DE_PASSE = "motdepasse-long-12"
LIEN_YOUTUBE = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


@pytest.fixture
def enseignant(db):
    compte = User.objects.create_user(
        username="prof_video", email="pv@iteag.org", password=MOT_DE_PASSE, role=User.Role.ENSEIGNANT
    )
    Professeur.objects.create(nom="Nisus", prenom="Alain", slug="nisus-video", user=compte)
    return compte


@pytest.fixture
def video(db, enseignant):
    return VideoAsset.objects.create(
        titre="Herméneutique — séance 1",
        cle_stockage="ancien-identifiant",
        fournisseur="youtube",
        duree_secondes=0,
        uploade_par=enseignant,
        statut_traitement=VideoAsset.StatutTraitement.PRET,
    )


def test_l_enseignant_corrige_le_titre_et_la_duree(client, enseignant, video):
    client.force_login(enseignant)

    reponse = client.post(
        reverse("elearning:enseignant_video_modifier", args=[video.pk]),
        {
            "titre": "Herméneutique — séance 1 (corrigé)",
            "adresse_video": LIEN_YOUTUBE,
            "duree_secondes": 1800,
            "transcription": "",
        },
    )

    assert reponse.status_code == 302
    video.refresh_from_db()
    assert video.titre == "Herméneutique — séance 1 (corrigé)"
    assert video.duree_secondes == 1800


def test_la_video_garde_son_identite(client, enseignant, video):
    """Corriger ne recrée pas : les leçons qui l'emploient doivent suivre."""
    identifiant = video.pk
    client.force_login(enseignant)

    client.post(
        reverse("elearning:enseignant_video_modifier", args=[video.pk]),
        {"titre": "Nouveau titre", "adresse_video": LIEN_YOUTUBE, "duree_secondes": "", "transcription": ""},
    )

    assert VideoAsset.objects.count() == 1
    assert VideoAsset.objects.get().pk == identifiant


def test_le_formulaire_est_prerempli(client, enseignant, video):
    client.force_login(enseignant)
    contenu = client.get(reverse("elearning:enseignant_video_modifier", args=[video.pk])).content.decode()
    assert "Herméneutique — séance 1" in contenu
    assert "Enregistrer les corrections" in contenu


def test_un_lien_invalide_est_refuse(client, enseignant, video):
    client.force_login(enseignant)

    client.post(
        reverse("elearning:enseignant_video_modifier", args=[video.pk]),
        {"titre": "Titre", "adresse_video": "pas-une-adresse", "duree_secondes": "", "transcription": ""},
    )

    video.refresh_from_db()
    assert video.titre == "Herméneutique — séance 1", "Un lien refusé ne doit rien enregistrer"


def test_on_ne_modifie_pas_la_video_d_un_collegue(client, db, video):
    """Le déposant fait autorité : un identifiant deviné ne suffit pas."""
    intrus = User.objects.create_user(
        username="intrus_video", email="iv@iteag.org", password=MOT_DE_PASSE, role=User.Role.ENSEIGNANT
    )
    Professeur.objects.create(nom="Intrus", prenom="Prof", slug="intrus-video", user=intrus)

    client.force_login(intrus)
    reponse = client.post(
        reverse("elearning:enseignant_video_modifier", args=[video.pk]),
        {"titre": "Détourné", "adresse_video": LIEN_YOUTUBE, "duree_secondes": "", "transcription": ""},
    )

    assert reponse.status_code == 404
    video.refresh_from_db()
    assert video.titre == "Herméneutique — séance 1"


def test_la_liste_propose_la_modification(client, enseignant, video):
    client.force_login(enseignant)
    contenu = client.get(reverse("elearning:enseignant_videos")).content.decode()
    assert reverse("elearning:enseignant_video_modifier", args=[video.pk]) in contenu
