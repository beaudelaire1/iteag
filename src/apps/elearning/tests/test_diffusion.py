"""
Tests de la couche de diffusion — ADR-005.

Deux choses se jouent ici. D'abord la signature Bunny, qui est déterministe et
se vérifie donc entièrement hors ligne : aucun compte n'est nécessaire pour
savoir si le jeton est correctement formé. Ensuite l'invariant de protection,
qui est le garde-fou du dispositif d'accès : sans lui, coller un identifiant
YouTube sur un module payant suffirait à tout ouvrir.
"""

import base64
import hashlib
import time

import pytest
from django.core.exceptions import ValidationError

from apps.elearning.diffusion import (
    FOURNISSEURS,
    BunnyStreamVideo,
    ModeLecture,
    NiveauProtection,
    VimeoVideo,
    YouTubeVideo,
    fournisseur,
    fournisseur_compatible,
    origines_actives,
    protection_suffisante,
)
from apps.elearning.models import Chapitre, Lecon, ModuleFormation, VideoAsset

# ══════════════════════════════════════════════
# Choix du fournisseur
# ══════════════════════════════════════════════


class TestSelection:
    def test_le_reglage_determine_le_fournisseur(self, settings):
        settings.ELEARNING_DIFFUSION_VIDEO = "youtube"
        assert fournisseur().nom == "youtube"

    def test_un_nom_explicite_l_emporte(self, settings):
        settings.ELEARNING_DIFFUSION_VIDEO = "youtube"
        assert fournisseur("local").nom == "local"

    def test_un_reglage_inconnu_retombe_sur_bunny(self, settings):
        """Une faute de frappe ne doit jamais réactiver le stockage local."""
        settings.ELEARNING_DIFFUSION_VIDEO = "fournisseur-inexistant"
        assert fournisseur().nom == "bunny"

    def test_tous_les_fournisseurs_declarent_leur_protection(self):
        for nom, classe in FOURNISSEURS.items():
            assert classe.protection in (
                NiveauProtection.AUCUNE,
                NiveauProtection.DOMAINE,
                NiveauProtection.SIGNEE,
            ), nom


# ══════════════════════════════════════════════
# Signature Bunny — vérifiable sans compte
# ══════════════════════════════════════════════


class TestJetonBunny:
    @pytest.fixture(autouse=True)
    def _config(self, settings):
        settings.BUNNY_ZONE_DIFFUSION = "https://iteag.b-cdn.net"
        settings.BUNNY_CLE_SIGNATURE = "cle-de-test-ne-servant-a-rien"
        settings.BUNNY_LIER_ADRESSE_IP = False

    def test_le_jeton_suit_l_algorithme_documente(self):
        """
        Le condensé porte sur clé + chemin + expiration, en base64 URL-safe.

        Ce test dit que le jeton est *formé* comme nous l'avons décidé. Il ne
        peut pas dire que le CDN l'*accepte* : cela ne se vérifie que contre le
        compte réel, ce que fait « manage.py verifier_bunny ».
        """
        backend = BunnyStreamVideo()
        chemin = "/abc/playlist.m3u8"
        expiration = 1800000000

        attendu = base64.b64encode(
            hashlib.sha256(f"cle-de-test-ne-servant-a-rien{chemin}{expiration}".encode()).digest()
        ).decode()
        attendu = attendu.replace("+", "-").replace("/", "_").replace("=", "")

        assert backend.jeton(chemin, expiration) == attendu

    def test_la_signature_porte_sur_le_repertoire_et_non_sur_le_manifeste(self):
        """
        Le défaut que ce test verrouille : un flux HLS n'est pas un fichier.
        Après le manifeste, le lecteur demande les segments un par un. Signer
        « /abc/playlist.m3u8 » laisse charger le manifeste puis fait refuser
        chaque segment — la lecture s'arrête après avoir paru fonctionner.
        """
        backend = BunnyStreamVideo()
        requete = backend.requete_signee("abc", 1800000000)

        assert "token_path=" in requete, "Sans « token_path », les segments seront refusés"
        assert "token_path=%2Fabc%2F" in requete, "Le répertoire signé doit être encodé dans l'adresse"

        # Le jeton doit être celui du répertoire, pas celui du manifeste.
        jeton_repertoire = backend.jeton("/abc/", 1800000000, "", {"token_path": "/abc/"})
        assert f"token={jeton_repertoire}" in requete

    def test_la_meme_requete_vaut_pour_le_manifeste_et_ses_segments(self):
        """C'est ce que le lecteur réapplique à chaque téléchargement."""
        backend = BunnyStreamVideo()
        expiration = 1800000000
        requete = backend.requete_signee("abc", expiration)
        lecture = backend.lecture("abc", ttl=300)
        # L'adresse de lecture porte la même chaîne, à l'expiration près.
        assert "token_path=%2Fabc%2F" in lecture.url
        assert requete.split("&token_path=")[1].split("&")[0] in lecture.url

    def test_le_repertoire_signe_est_normalise(self):
        """Un identifiant collé avec des barres obliques ne doit pas changer la signature."""
        assert BunnyStreamVideo.repertoire("abc") == "/abc/"
        assert BunnyStreamVideo.repertoire("/abc/") == "/abc/"

    def test_deux_videos_ne_partagent_pas_le_meme_jeton(self):
        """Sans quoi l'accès à une vidéo ouvrirait toute la bibliothèque."""
        backend = BunnyStreamVideo()
        assert backend.requete_signee("abc", 1800000000) != backend.requete_signee("def", 1800000000)

    def test_le_jeton_ne_contient_aucun_caractere_hostile_a_une_url(self):
        jeton = BunnyStreamVideo().jeton("/abc/playlist.m3u8", 1800000000)
        assert "+" not in jeton
        assert "/" not in jeton
        assert "=" not in jeton

    def test_la_cle_secrete_ne_figure_pas_dans_l_adresse(self):
        adresse = BunnyStreamVideo().lecture("abc").url
        assert "cle-de-test" not in adresse

    def test_l_adresse_porte_le_manifeste_et_l_expiration(self):
        lecture = BunnyStreamVideo().lecture("abc", ttl=300)
        assert lecture.mode == ModeLecture.HLS
        assert "/abc/playlist.m3u8" in lecture.url
        assert "token=" in lecture.url and "expires=" in lecture.url
        assert lecture.expire_dans == 300

    def test_l_expiration_est_dans_le_futur_proche(self):
        lecture = BunnyStreamVideo().lecture("abc", ttl=300)
        expiration = int(lecture.url.split("expires=")[1])
        assert 0 < expiration - int(time.time()) <= 300

    def test_deux_ttl_differents_donnent_deux_jetons_differents(self):
        backend = BunnyStreamVideo()
        assert backend.jeton("/a/playlist.m3u8", 1) != backend.jeton("/a/playlist.m3u8", 2)

    def test_l_adresse_ip_est_ignoree_quand_la_liaison_est_inactive(self, settings):
        settings.BUNNY_LIER_ADRESSE_IP = False
        backend = BunnyStreamVideo()
        sans = backend.lecture("abc", ttl=300, adresse_ip="")
        avec = backend.lecture("abc", ttl=300, adresse_ip="203.0.113.9")
        assert sans.url.split("token=")[1] == avec.url.split("token=")[1]

    def test_l_adresse_ip_change_le_jeton_quand_la_liaison_est_active(self, settings):
        settings.BUNNY_LIER_ADRESSE_IP = True
        backend = BunnyStreamVideo()
        sans = backend.jeton("/abc/playlist.m3u8", 1800000000, "")
        avec = backend.jeton("/abc/playlist.m3u8", 1800000000, "203.0.113.9")
        assert sans != avec

    def test_le_televersement_est_refuse_explicitement(self):
        """Mieux vaut une erreur claire qu'un dépôt qui semble réussir sans rien faire."""
        with pytest.raises(NotImplementedError):
            BunnyStreamVideo().televerser(None, "abc")


# ══════════════════════════════════════════════
# Fournisseurs en cadre
# ══════════════════════════════════════════════


class TestFournisseursIframe:
    def test_youtube_utilise_le_domaine_sans_traceur(self):
        lecture = YouTubeVideo().lecture("dQw4w9WgXcQ")
        assert lecture.url.startswith("https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ")
        assert lecture.mode == ModeLecture.IFRAME

    def test_vimeo_pointe_le_lecteur(self):
        assert VimeoVideo().lecture("123456789").url.startswith("https://player.vimeo.com/video/123456789")

    def test_youtube_n_offre_aucune_protection(self):
        assert YouTubeVideo.protection == NiveauProtection.AUCUNE

    def test_vimeo_protege_le_domaine_pas_la_personne(self):
        assert VimeoVideo.protection == NiveauProtection.DOMAINE


# ══════════════════════════════════════════════
# Origines autorisées dans la CSP
# ══════════════════════════════════════════════


class TestOriginesCsp:
    def test_les_fournisseurs_de_liens_sont_toujours_autorises(self, settings):
        settings.ELEARNING_DIFFUSION_VIDEO = "local"
        settings.ELEARNING_DIFFUSION_PUBLIQUE = []
        settings.BUNNY_ZONE_DIFFUSION = ""
        assert origines_actives() == [
            "https://player.vimeo.com",
            "https://www.youtube-nocookie.com",
        ]

    def test_youtube_public_ouvre_son_origine(self, settings):
        settings.ELEARNING_DIFFUSION_VIDEO = "local"
        settings.ELEARNING_DIFFUSION_PUBLIQUE = ["youtube"]
        settings.BUNNY_ZONE_DIFFUSION = ""
        assert "https://www.youtube-nocookie.com" in origines_actives()

    def test_l_origine_bunny_vient_du_reglage(self, settings):
        """Elle est calculée, pas codée en dur : c'est la zone du client."""
        settings.ELEARNING_DIFFUSION_VIDEO = "bunny"
        settings.ELEARNING_DIFFUSION_PUBLIQUE = []
        settings.BUNNY_ZONE_DIFFUSION = "https://iteag.b-cdn.net"
        assert "https://iteag.b-cdn.net" in origines_actives()

    def test_bunny_sans_zone_configuree_n_ouvre_rien(self, settings):
        settings.ELEARNING_DIFFUSION_VIDEO = "bunny"
        settings.ELEARNING_DIFFUSION_PUBLIQUE = []
        settings.BUNNY_ZONE_DIFFUSION = ""
        assert all("b-cdn.net" not in origine for origine in origines_actives())


# ══════════════════════════════════════════════
# L'invariant de protection
# ══════════════════════════════════════════════


class TestProtectionSuffisante:
    @pytest.mark.parametrize(
        ("protection", "politique", "attendu"),
        [
            # Un module public accepte tout.
            (NiveauProtection.AUCUNE, "public", True),
            (NiveauProtection.DOMAINE, "public", True),
            (NiveauProtection.SIGNEE, "public", True),
            # Réservé aux comptes : un lien porteur contournerait la connexion.
            (NiveauProtection.AUCUNE, "authentifie", False),
            (NiveauProtection.DOMAINE, "authentifie", True),
            (NiveauProtection.SIGNEE, "authentifie", True),
            # Droit individuel : seule une adresse signée se retire.
            (NiveauProtection.AUCUNE, "inscrit_parcours", False),
            (NiveauProtection.DOMAINE, "inscrit_parcours", False),
            (NiveauProtection.SIGNEE, "inscrit_parcours", True),
            (NiveauProtection.AUCUNE, "sur_octroi", False),
            (NiveauProtection.DOMAINE, "sur_octroi", False),
            (NiveauProtection.SIGNEE, "sur_octroi", True),
        ],
    )
    def test_table_de_verite(self, protection, politique, attendu):
        assert protection_suffisante(protection, politique) is attendu

    def test_une_politique_inconnue_exige_le_maximum(self):
        """Devant l'inconnu, on refuse — l'inverse ouvrirait une brèche silencieuse."""
        assert protection_suffisante(NiveauProtection.DOMAINE, "politique-inventee") is False
        assert protection_suffisante(NiveauProtection.SIGNEE, "politique-inventee") is True

    def test_une_protection_inconnue_est_refusee(self):
        assert protection_suffisante("protection-inventee", "public") is False

    def test_youtube_peut_etre_essaye_sur_un_module_protege_en_dev(self, settings):
        settings.DEBUG = True
        settings.ELEARNING_AUTORISER_VIDEO_PUBLIQUE_EN_DEV = True
        assert fournisseur_compatible("youtube", "inscrit_parcours") is True

    def test_la_derogation_dev_ne_s_applique_jamais_sans_debug(self, settings):
        settings.DEBUG = False
        settings.ELEARNING_AUTORISER_VIDEO_PUBLIQUE_EN_DEV = True
        assert fournisseur_compatible("youtube", "inscrit_parcours") is False


@pytest.mark.django_db
class TestInvariantSurLaLecon:
    """L'invariant appliqué à travers le modèle — le vrai garde-fou."""

    def _module(self, politique):
        return ModuleFormation.objects.create(
            titre="Module test", slug=f"module-{politique}", politique_acces=politique
        )

    def _lecon(self, module, fournisseur_video):
        chapitre = Chapitre.objects.create(module=module, titre="Chapitre", ordre=1)
        video = VideoAsset.objects.create(
            titre="Vidéo",
            cle_stockage=f"cle-{module.slug}-{fournisseur_video}",
            fournisseur=fournisseur_video,
            statut_traitement=VideoAsset.StatutTraitement.PRET,
        )
        return Lecon(
            chapitre=chapitre,
            titre="Leçon",
            slug="lecon",
            ordre=1,
            type_lecon=Lecon.TypeLecon.VIDEO,
            video=video,
        )

    def test_youtube_est_refuse_sur_un_module_sur_octroi(self):
        lecon = self._lecon(self._module("sur_octroi"), "youtube")
        with pytest.raises(ValidationError) as erreur:
            lecon.full_clean()
        assert "video" in erreur.value.error_dict

    def test_vimeo_est_refuse_sur_un_module_sur_octroi(self):
        lecon = self._lecon(self._module("sur_octroi"), "vimeo")
        with pytest.raises(ValidationError):
            lecon.full_clean()

    def test_bunny_est_accepte_sur_un_module_sur_octroi(self):
        lecon = self._lecon(self._module("sur_octroi"), "bunny")
        lecon.full_clean()  # ne lève pas

    def test_youtube_est_accepte_sur_un_module_public(self):
        lecon = self._lecon(self._module("public"), "youtube")
        lecon.full_clean()  # ne lève pas

    def test_le_message_nomme_le_fournisseur_et_la_politique(self):
        """Un refus doit dire quoi corriger, pas seulement qu'il y a un problème."""
        lecon = self._lecon(self._module("inscrit_parcours"), "youtube")
        with pytest.raises(ValidationError) as erreur:
            lecon.full_clean()
        message = str(erreur.value)
        assert "YouTube" in message
        assert "signée" in message

    def test_la_publication_refuse_un_fournisseur_trop_faible(self):
        """
        Second filet : la politique a pu être resserrée après le rattachement,
        auquel cas la validation de la leçon n'a jamais été rejouée.
        """
        module = self._module("public")
        lecon = self._lecon(module, "youtube")
        lecon.save()

        module.politique_acces = ModuleFormation.PolitiqueAcces.SUR_OCTROI
        module.save(update_fields=["politique_acces"])

        possible, motif = module.peut_etre_publie()
        assert possible is False
        assert "retirer" in motif

    def test_la_publication_accepte_un_fournisseur_signe(self):
        module = self._module("sur_octroi")
        self._lecon(module, "bunny").save()
        possible, motif = module.peut_etre_publie()
        assert possible is True, motif


@pytest.mark.django_db
class TestModeLecture:
    def test_chaque_fournisseur_expose_son_mode(self):
        for nom, classe in FOURNISSEURS.items():
            video = VideoAsset.objects.create(titre="V", cle_stockage=f"c-{nom}", fournisseur=nom)
            assert video.mode_lecture == classe.mode

    def test_un_fournisseur_inconnu_retombe_sur_le_mode_hls_externe(self):
        video = VideoAsset.objects.create(titre="V", cle_stockage="c-x", fournisseur="inconnu")
        assert video.mode_lecture == BunnyStreamVideo.mode


@pytest.mark.django_db
class TestCspSurLaReponse:
    """
    L'ouverture doit atteindre l'en-tête réel : une directive calculée mais
    jamais posée protégerait sur le papier et casserait la lecture en vrai.
    """

    @pytest.fixture
    def module_public(self):
        module = ModuleFormation.objects.create(
            titre="Module vitrine",
            slug="module-vitrine",
            politique_acces=ModuleFormation.PolitiqueAcces.PUBLIC,
            statut=ModuleFormation.StatutPublication.PUBLIE,
        )
        chapitre = Chapitre.objects.create(module=module, titre="Chapitre", ordre=1)
        video = VideoAsset.objects.create(
            titre="Bande-annonce",
            cle_stockage="dQw4w9WgXcQ",
            fournisseur="youtube",
            statut_traitement=VideoAsset.StatutTraitement.PRET,
        )
        Lecon.objects.create(
            chapitre=chapitre,
            titre="Présentation",
            slug="presentation",
            ordre=1,
            type_lecon=Lecon.TypeLecon.VIDEO,
            video=video,
            apercu_gratuit=True,
        )
        return module

    def test_l_origine_publique_figure_dans_l_en_tete(self, client, module_public, settings):
        settings.CONTENT_SECURITY_POLICY = {"DIRECTIVES": {"default-src": ["'self'"], "frame-src": ["'none'"]}}
        settings.ELEARNING_DIFFUSION_PUBLIQUE = ["youtube"]

        reponse = client.get(module_public.get_absolute_url())
        entete = reponse.headers.get("Content-Security-Policy", "")
        assert "https://www.youtube-nocookie.com" in entete
        # « 'none' » doit avoir disparu : la spécification le veut seul.
        assert "frame-src 'none'" not in entete

    def test_les_fournisseurs_acceptes_restent_limites_a_la_liste_blanche(self, client, module_public, settings):
        settings.CONTENT_SECURITY_POLICY = {"DIRECTIVES": {"default-src": ["'self'"], "frame-src": ["'none'"]}}
        settings.ELEARNING_DIFFUSION_VIDEO = "local"
        settings.ELEARNING_DIFFUSION_PUBLIQUE = []

        reponse = client.get(module_public.get_absolute_url())
        entete = reponse.headers.get("Content-Security-Policy", "")
        assert "https://www.youtube-nocookie.com" in entete
        assert "https://player.vimeo.com" in entete
        assert "frame-src 'none'" not in entete
