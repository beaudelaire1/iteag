"""
Déposer une vidéo depuis la plateforme, sans compte chez l'hébergeur.

Le référencement supposait que l'enseignant ait déjà déposé sa vidéo chez Bunny,
Vimeo ou YouTube, puis en recopie l'identifiant. Pour un institut qui découpe
une prédication de trois heures en six séquences, cela faisait six dépôts
manuels et six identifiants à recopier avant de toucher à la plateforme.

Le dépôt vise Bunny seul, et ce n'est pas une omission : le modèle de diffusion
réserve les modules restreints aux adresses signées, et déclare YouTube comme
Vimeo « contenu public ». Offrir le choix laisserait déposer un cours là où
l'accès ne se retire pas.
"""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.accounts.models import User
from apps.elearning import bunny_televersement as bunny
from apps.elearning.models import VideoAsset
from apps.formations.models import Professeur

pytestmark = pytest.mark.django_db

MOT_DE_PASSE = "motdepasse-long-12"

# Boîte ISO Base Media minimale : la taille précède le type, « ftyp » se lit
# donc au cinquième octet. C'est exactement ce que le validateur contrôle.
MP4 = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom" + b"\x00" * 64


@pytest.fixture
def enseignant(db):
    compte = User.objects.create_user(
        username="prof_depot", email="pd@iteag.org", password=MOT_DE_PASSE, role=User.Role.ENSEIGNANT
    )
    Professeur.objects.create(nom="Labeth", prenom="Ruth", slug="labeth-depot", user=compte)
    return compte


def fichier(nom="sequence-1.mp4", contenu=MP4, type_mime="video/mp4"):
    return SimpleUploadedFile(nom, contenu, content_type=type_mime)


# Bunny délivre des clés de découpages variés ; la plateforme ne vérifie donc
# que le jeu de caractères et une longueur plancher. Le jeu d'essai porte l'un
# des découpages observés — factice, mais plausible.
CLE_BIEN_FORMEE = "0f8e1c2a-3b4d-4e5f-8a9b-0c1d2e3f4a5b"


@pytest.fixture
def bunny_configure(settings):
    settings.BUNNY_STREAM_LIBRARY_ID = "12345"
    settings.BUNNY_STREAM_API_KEY = CLE_BIEN_FORMEE


class TestSignatureVideo:
    """Le validateur commun refusait toute vidéo, faute de signature connue."""

    def test_un_mp4_est_reconnu(self):
        from apps.core.validation_fichiers import valider_fichier
        from apps.elearning.forms import REGLE_VIDEO

        valider_fichier(fichier(), REGLE_VIDEO)

    def test_un_fichier_renomme_en_mp4_est_refuse(self):
        """Une extension ne prouve rien : c'est la signature qui tranche."""
        from django import forms

        from apps.core.validation_fichiers import valider_fichier
        from apps.elearning.forms import REGLE_VIDEO

        with pytest.raises(forms.ValidationError):
            valider_fichier(fichier(contenu=b"<html>pas une video</html>" * 8), REGLE_VIDEO)

    def test_un_webm_est_reconnu(self):
        from apps.core.validation_fichiers import valider_fichier
        from apps.elearning.forms import REGLE_VIDEO

        ebml = b"\x1a\x45\xdf\xa3" + b"\x00" * 80
        valider_fichier(fichier("sequence.webm", ebml, "video/webm"), REGLE_VIDEO)


class TestDepotDepuisLaPlateforme:
    def test_le_depot_declare_la_video_et_confie_l_envoi(self, client, enseignant, bunny_configure, monkeypatch):
        appels = {}

        def declarer(titre):
            appels["titre"] = titre
            return "guid-bunny"

        monkeypatch.setattr(bunny, "creer_video", declarer)
        monkeypatch.setattr(
            "apps.elearning.tasks.televerser_video_bunny.delay",
            lambda video_id: appels.setdefault("tache", video_id),
        )

        client.force_login(enseignant)
        reponse = client.post(
            reverse("elearning:enseignant_videos"),
            {"action": "deposer", "titre": "Prédication — séquence 1", "fichier": fichier(), "transcription": ""},
        )

        assert reponse.status_code == 302, reponse.context["form"].errors
        video = VideoAsset.objects.get()
        assert video.cle_stockage == "guid-bunny"
        assert video.fournisseur == "bunny"
        assert video.statut_traitement == VideoAsset.StatutTraitement.EN_ATTENTE
        assert video.fichier_source
        assert appels["tache"] == str(video.pk)

    def test_un_refus_de_bunny_fait_heberger_la_video_par_l_institut(
        self, client, enseignant, bunny_configure, monkeypatch
    ):
        """Le refus de Bunny ne doit plus coûter la vidéo.

        Il faisait échouer le dépôt et renvoyait l'enseignant à une variable
        d'environnement qu'il n'a aucun moyen de corriger. La vidéo est donc
        gardée ici, servie par la même adresse signée, et l'enseignant sait
        qu'il faut le signaler.
        """

        def refuser(_titre):
            raise bunny.TeleversementBunnyIndisponible("Bunny a refusé l'appel (401).")

        monkeypatch.setattr(bunny, "creer_video", refuser)

        client.force_login(enseignant)
        reponse = client.post(
            reverse("elearning:enseignant_videos"),
            {"action": "deposer", "titre": "Prédication", "fichier": fichier(), "transcription": ""},
            follow=True,
        )

        assert reponse.status_code == 200
        video = VideoAsset.objects.get()
        assert video.fournisseur == "local"
        assert video.statut_traitement == VideoAsset.StatutTraitement.PRET
        # Une adresse signée, comme chez Bunny : le module restreint reste servi.
        from apps.elearning.diffusion import NiveauProtection

        assert video.protection == NiveauProtection.SIGNEE
        assert any("hébergée par ITEAG" in str(message) for message in reponse.context["messages"])

    def test_sans_cle_api_le_depot_reste_propose(self, client, enseignant, settings):
        """Sans clé, le dépôt reste le seul geste qu'un enseignant sache faire.

        L'écran le retirait, ne laissant que le référencement — c'est-à-dire un
        compte Bunny, que l'enseignant n'a pas et n'a pas à avoir. Le dépôt tient
        désormais sans Bunny ; l'écran le propose donc, en disant qui hébergera.
        """
        settings.BUNNY_STREAM_LIBRARY_ID = ""
        settings.BUNNY_STREAM_API_KEY = ""

        client.force_login(enseignant)
        contenu = client.get(reverse("elearning:enseignant_videos")).content.decode()

        assert "Déposer un fichier" in contenu
        assert "hébergée par" in contenu

    def test_un_fichier_qui_n_est_pas_une_video_est_refuse(self, client, enseignant, bunny_configure):
        client.force_login(enseignant)
        reponse = client.post(
            reverse("elearning:enseignant_videos"),
            {
                "action": "deposer",
                "titre": "Prédication",
                "fichier": SimpleUploadedFile("notes.pdf", b"%PDF-1.4 ...", content_type="application/pdf"),
                "transcription": "",
            },
        )

        assert reponse.status_code == 200
        assert not VideoAsset.objects.exists()


class TestDepuisLaLecon:
    """
    La vidéo se choisissait dans une liste que rien ne remplissait depuis là.

    Il fallait quitter la leçon, passer par la bibliothèque, revenir. Pour une
    prédication découpée en six séquences : six allers-retours.
    """

    @pytest.fixture
    def chapitre(self, enseignant):
        from apps.elearning.models import Chapitre, ModuleFormation

        module = ModuleFormation.objects.create(
            titre="Atelier de prédication", slug="atelier-lecon", responsable=enseignant.profil_professeur
        )
        return Chapitre.objects.create(module=module, titre="Séquences", ordre=1)

    def saisie(self, **extra):
        donnees = {
            "titre": "Séquence 1",
            "type_lecon": "video",
            "ordre": "0",
            "duree_secondes": "",
            "contenu_texte": "",
            "lien_externe": "",
        }
        donnees.update(extra)
        return donnees

    def test_le_fichier_depose_devient_la_video_de_la_lecon(
        self, client, enseignant, chapitre, bunny_configure, monkeypatch
    ):
        envois = {}
        monkeypatch.setattr(bunny, "creer_video", lambda titre: "guid-lecon")
        monkeypatch.setattr(
            "apps.elearning.tasks.televerser_video_bunny.delay",
            lambda video_id: envois.setdefault("tache", video_id),
        )

        client.force_login(enseignant)
        reponse = client.post(
            reverse("elearning:enseignant_lecon_creer", args=[chapitre.pk]),
            self.saisie(video_fichier=fichier()),
        )

        assert reponse.status_code == 302, reponse.context["form"].errors
        video = VideoAsset.objects.get()
        assert video.cle_stockage == "guid-lecon"
        assert video.fournisseur == "bunny"
        assert chapitre.lecons.get().video == video
        assert envois["tache"] == str(video.pk)

    def test_un_lien_youtube_designe_son_hebergeur(self, client, enseignant, chapitre):
        """
        L'hébergeur découle de l'adresse : rien à cocher.

        YouTube n'est admis que sur un module public. Le modèle refuse de le
        rattacher à un module réservé, dont l'accès doit pouvoir être retiré —
        et une adresse YouTube partagée ne se retire pas.
        """
        from apps.elearning.models import ModuleFormation

        module = chapitre.module
        module.politique_acces = ModuleFormation.PolitiqueAcces.PUBLIC
        module.save(update_fields=["politique_acces"])

        client.force_login(enseignant)
        reponse = client.post(
            reverse("elearning:enseignant_lecon_creer", args=[chapitre.pk]),
            self.saisie(video_lien="https://www.youtube.com/watch?v=dQw4w9WgXcQ"),
        )

        assert reponse.status_code == 302, reponse.context["form"].errors
        video = VideoAsset.objects.get()
        assert video.fournisseur == "youtube"
        assert video.statut_traitement == VideoAsset.StatutTraitement.PRET

    def test_deux_sources_a_la_fois_sont_refusees(self, client, enseignant, chapitre, bunny_configure):
        client.force_login(enseignant)
        reponse = client.post(
            reverse("elearning:enseignant_lecon_creer", args=[chapitre.pk]),
            self.saisie(video_fichier=fichier(), video_lien="https://www.youtube.com/watch?v=dQw4w9WgXcQ"),
        )

        assert reponse.status_code == 200
        assert not VideoAsset.objects.exists()

    def test_une_lecon_video_sans_source_est_refusee(self, client, enseignant, chapitre):
        client.force_login(enseignant)
        reponse = client.post(reverse("elearning:enseignant_lecon_creer", args=[chapitre.pk]), self.saisie())

        assert reponse.status_code == 200
        assert not chapitre.lecons.exists()

    def test_rien_n_est_declare_chez_l_hebergeur_si_la_lecon_est_refusee(
        self, client, enseignant, chapitre, bunny_configure, monkeypatch
    ):
        """Un formulaire qui échoue ne doit pas laisser une vidée orpheline chez Bunny."""
        appels = []
        monkeypatch.setattr(bunny, "creer_video", lambda titre: appels.append(titre) or "guid")

        client.force_login(enseignant)
        client.post(
            reverse("elearning:enseignant_lecon_creer", args=[chapitre.pk]),
            self.saisie(titre="", video_fichier=fichier()),
        )

        assert appels == []
        assert not VideoAsset.objects.exists()

    def test_un_depot_refuse_n_empeche_plus_la_lecon(self, client, enseignant, chapitre, bunny_configure, monkeypatch):
        """Refusé, le dépôt fermait tout — la leçon, et donc ses ressources.

        L'écran des ressources n'est servi qu'aux leçons existantes. Une leçon
        vidéo qu'on ne peut pas créer emportait donc avec elle la possibilité de
        lui attacher quoi que ce soit : une clé mal recopiée suffisait à fermer
        la création de cours à tout l'institut. La leçon se crée désormais, sa
        vidéo est hébergée ici, et l'enseignant est prévenu de le signaler.
        """
        from apps.elearning.models import Lecon

        def refuser(_titre):
            raise bunny.TeleversementBunnyIndisponible(bunny.MESSAGE_CLE_REFUSEE)

        monkeypatch.setattr(bunny, "creer_video", refuser)

        client.force_login(enseignant)
        reponse = client.post(
            reverse("elearning:enseignant_lecon_creer", args=[chapitre.pk]),
            self.saisie(video_fichier=fichier()),
            follow=True,
        )

        assert reponse.status_code == 200
        lecon = Lecon.objects.get()
        assert lecon.video is not None
        assert lecon.video.fournisseur == "local"
        assert any("hébergée par ITEAG" in str(message) for message in reponse.context["messages"])


class TestTacheDEnvoi:
    @pytest.fixture
    def video(self, enseignant):
        return VideoAsset.objects.create(
            titre="Prédication — séquence 1",
            cle_stockage="guid-bunny",
            fournisseur="bunny",
            fichier_source=fichier(),
            uploade_par=enseignant,
            statut_traitement=VideoAsset.StatutTraitement.EN_ATTENTE,
        )

    def test_l_envoi_reussi_efface_le_fichier_et_marque_prete(self, video, bunny_configure, monkeypatch):
        """La plateforme convoie la vidéo, elle ne l'héberge pas."""
        from apps.elearning.tasks import televerser_video_bunny

        monkeypatch.setattr(bunny, "envoyer_fichier", lambda *args: None)
        monkeypatch.setattr(bunny, "etat_video", lambda _id: bunny.ETAT_TERMINE)
        monkeypatch.setattr(bunny, "duree_video", lambda _id: 1234)

        assert televerser_video_bunny(str(video.pk)) == "pret"

        video.refresh_from_db()
        assert video.statut_traitement == VideoAsset.StatutTraitement.PRET
        assert video.duree_secondes == 1234
        assert not video.fichier_source

    def test_un_echec_bunny_laisse_la_raison_sur_la_fiche(self, video, bunny_configure, monkeypatch):
        from apps.elearning.tasks import televerser_video_bunny

        monkeypatch.setattr(bunny, "envoyer_fichier", lambda *args: None)
        monkeypatch.setattr(bunny, "etat_video", lambda _id: bunny.ETAT_ECHEC)

        assert televerser_video_bunny(str(video.pk)) == "erreur"

        video.refresh_from_db()
        assert video.statut_traitement == VideoAsset.StatutTraitement.ERREUR
        assert "rejeté" in video.message_erreur
        # Le fichier reste : il permet de relancer l'envoi sans le redemander.
        assert video.fichier_source


class TestClesRefusees:
    """Un 401 de Bunny ne dit jamais laquelle des deux clés est en cause."""

    def test_un_401_nomme_la_cle_a_corriger(self, bunny_configure, monkeypatch):
        """Le JSON brut de Bunny n'apprenait rien à qui le lisait dans le formulaire.

        « Authentication has been denied for this request » désigne un refus, pas
        une cause : la bibliothèque Stream porte deux clés, à deux endroits de la
        même page, et les confondre produit exactement ce message.
        """
        import io
        from urllib.error import HTTPError

        def refuser(*_args, **_kwargs):
            raise HTTPError(
                "https://video.bunnycdn.com/library/12345/videos",
                401,
                "Unauthorized",
                {},
                io.BytesIO(b'{"Success":false,"Message":"Authentication has been denied for this request."}'),
            )

        monkeypatch.setattr(bunny, "urlopen", refuser)

        with pytest.raises(bunny.TeleversementBunnyIndisponible) as refus:
            bunny.creer_video("Prédication")

        message = str(refus.value)
        assert "BUNNY_STREAM_API_KEY" in message
        assert "authentification par jeton" in message
        # Le corps de Bunny part au journal, pas sous les yeux de l'utilisateur.
        assert "Authentication has been denied" not in message

    def test_un_autre_code_garde_le_detail_de_bunny(self, bunny_configure, monkeypatch):
        """Hors identifiants, le corps de Bunny nomme souvent la cause : on le garde."""
        import io
        from urllib.error import HTTPError

        def refuser(*_args, **_kwargs):
            raise HTTPError(
                "https://video.bunnycdn.com/library/12345/videos",
                429,
                "Too Many Requests",
                {},
                io.BytesIO(b'{"Message":"Quota depasse"}'),
            )

        monkeypatch.setattr(bunny, "urlopen", refuser)

        with pytest.raises(bunny.TeleversementBunnyIndisponible, match="Quota depasse"):
            bunny.creer_video("Prédication")


class TestFormeDesIdentifiants:
    """
    Une clé recopiée de travers produit le même refus qu'une clé fausse.

    Une valeur qui traîne une espace ou un retour à la ligne passe le contrôle
    de présence, puis Bunny répond « Authentication has been denied » et
    l'exploitant relit une clé qu'il croit bonne en cherchant du côté du compte
    Bunny. Ce défaut-là se contrôle ici, avant tout appel, parce qu'il est
    certain.

    Ce qui n'est pas certain, en revanche, c'est le découpage en groupes. Ce
    module a exigé un identifiant universel jusqu'au 10 septembre 2026, jour où
    il a refusé une clé authentique de six groupes et bloqué tout dépôt sur
    l'instance en service. Le contrôle ne juge donc plus la forme des groupes.
    """

    def test_une_cle_a_six_groupes_passe(self, settings):
        """Le cas réel : Bunny délivre aussi des clés en 8-4-4-12-4-4."""
        settings.BUNNY_STREAM_LIBRARY_ID = "712346"

        assert bunny.defaut_de_forme("712346", "0f8e1c2a-3b4d-4e5f-0c1d2e3f4a5b-8a9b-1234") == ""

    def test_une_cle_coupee_par_une_espace_est_refusee_avant_tout_appel(self, settings, monkeypatch):
        """Une espace au milieu, elle, est une erreur certaine.

        Les espaces de bord sont déjà retirées à la lecture du réglage : seule
        celle qui coupe la valeur en deux survit jusqu'ici, et elle vient
        toujours d'une sélection à la souris qui a ramassé de travers.
        """

        def jamais(*_args, **_kwargs):
            raise AssertionError("Aucun appel ne doit partir sur une clé mal formée.")

        monkeypatch.setattr(bunny, "urlopen", jamais)
        settings.BUNNY_STREAM_LIBRARY_ID = "712346"
        settings.BUNNY_STREAM_API_KEY = "0f8e1c2a-3b4d-4e5f 8a9b-0c1d2e3f4a5b"

        with pytest.raises(bunny.TeleversementBunnyIndisponible) as refus:
            bunny.creer_video("Prédication")

        message = str(refus.value)
        assert "BUNNY_STREAM_API_KEY" in message
        # Le secret ne se recopie ni dans un écran ni dans un journal.
        assert "0f8e1c2a" not in message

    def test_un_identifiant_de_bibliotheque_non_numerique_est_refuse(self, settings):
        settings.BUNNY_STREAM_LIBRARY_ID = "vz-7fd6c2-31c"
        settings.BUNNY_STREAM_API_KEY = CLE_BIEN_FORMEE

        with pytest.raises(bunny.TeleversementBunnyIndisponible, match="BUNNY_STREAM_LIBRARY_ID"):
            bunny.creer_video("Prédication")

    def test_une_cle_bien_formee_laisse_passer(self):
        assert bunny.defaut_de_forme("712346", CLE_BIEN_FORMEE) == ""

    def test_la_commande_nomme_le_defaut_de_forme(self, settings, monkeypatch):
        """`verifier_bunny` doit dire la même chose que l'écran, sans partir sur le réseau."""
        import io as flux

        from django.core.management import call_command
        from django.core.management.base import CommandError

        def jamais(*_args, **_kwargs):
            raise AssertionError("Aucun appel ne doit partir sur une clé mal formée.")

        monkeypatch.setattr(bunny, "urlopen", jamais)
        settings.BUNNY_STREAM_LIBRARY_ID = "712346"
        settings.BUNNY_STREAM_API_KEY = "0f8e1c2a-3b4d"

        with pytest.raises(CommandError, match="tronquée"):
            call_command("verifier_bunny", stdout=flux.StringIO())


class TestVerificationDesCles:
    """`verifier_bunny` n'éprouvait que la lecture — le dépôt passait au travers."""

    def commande(self, *args):
        import io as flux

        from django.core.management import call_command

        sortie = flux.StringIO()
        call_command("verifier_bunny", *args, stdout=sortie)
        return sortie.getvalue()

    def test_la_cle_de_depot_s_eprouve_sans_identifiant_de_video(self, bunny_configure, monkeypatch):
        """Le contrôle qui ne demande rien à personne doit pouvoir se lancer seul."""
        monkeypatch.setattr(bunny, "verifier_acces", lambda: 7)

        sortie = self.commande()

        assert "7 vidéo(s)" in sortie
        assert "Non éprouvée" in sortie

    def test_une_cle_de_depot_refusee_arrete_la_commande(self, bunny_configure, monkeypatch):
        """Un dépôt refusé n'est pas un avertissement : plus aucune leçon vidéo ne se crée."""
        from django.core.management.base import CommandError

        def refuser():
            raise bunny.TeleversementBunnyIndisponible(bunny.MESSAGE_CLE_REFUSEE)

        monkeypatch.setattr(bunny, "verifier_acces", refuser)

        with pytest.raises(CommandError, match="BUNNY_STREAM_API_KEY"):
            self.commande()

    def test_un_depot_non_configure_reste_un_avertissement(self, settings, monkeypatch):
        """Le dépôt est facultatif : sans clé, l'écran propose le lien, et c'est tout."""
        settings.BUNNY_STREAM_LIBRARY_ID = ""
        settings.BUNNY_STREAM_API_KEY = ""

        sortie = self.commande()

        assert "Dépôt non configuré" in sortie
