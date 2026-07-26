"""
Tests du portail enseignant.

L'enjeu principal n'est pas l'affichage : c'est le cloisonnement. Un enseignant
ne doit ni voir ni modifier le module d'un autre, et la publication ne doit pas
pouvoir livrer un module dont une vidéo n'est pas prête.
"""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.accounts.models import User
from apps.elearning.models import Chapitre, Lecon, ModuleFormation, SousTitre, VideoAsset
from apps.formations.models import Professeur


@pytest.fixture
def autre_enseignant(db):
    utilisateur = User.objects.create_user(
        username="autreprof",
        email="autreprof@iteag.org",
        password="motdepasse-long-12",
        role=User.Role.ENSEIGNANT,
    )
    return Professeur.objects.create(user=utilisateur, nom="Labeth", prenom="Ruth", slug="ruth-labeth")


@pytest.mark.django_db
class TestCloisonnementEntreEnseignants:
    def test_je_ne_vois_que_mes_modules(self, client, enseignant, autre_enseignant, module, discipline):
        ModuleFormation.objects.create(
            titre="Module d'un autre", slug="module-autre", discipline=discipline, responsable=autre_enseignant
        )
        client.force_login(enseignant.user)
        contenu = client.get(reverse("elearning:enseignant_modules")).content.decode()
        assert module.titre in contenu
        assert "Module d'un autre" not in contenu

    def test_je_ne_peux_pas_ouvrir_la_structure_d_un_autre(self, client, autre_enseignant, module, enseignant):
        client.force_login(autre_enseignant.user)
        reponse = client.get(reverse("elearning:enseignant_structure", kwargs={"slug": module.slug}))
        assert reponse.status_code == 404

    def test_je_ne_peux_pas_publier_le_module_d_un_autre(self, client, autre_enseignant, module):
        client.force_login(autre_enseignant.user)
        reponse = client.post(reverse("elearning:enseignant_publier", kwargs={"slug": module.slug}))
        assert reponse.status_code == 404

    def test_je_ne_peux_pas_supprimer_la_lecon_d_un_autre(self, client, autre_enseignant, lecon):
        client.force_login(autre_enseignant.user)
        reponse = client.post(reverse("elearning:enseignant_lecon_supprimer", kwargs={"pk": lecon.pk}))
        assert reponse.status_code == 404
        assert Lecon.objects.filter(pk=lecon.pk).exists()

    def test_un_etudiant_n_accede_pas_au_portail(self, client, utilisateur_etudiant):
        client.force_login(utilisateur_etudiant)
        reponse = client.get(reverse("elearning:enseignant_modules"))
        assert reponse.status_code in (302, 403)


@pytest.mark.django_db
class TestCycleDeVieDUnModule:
    def test_creation(self, client, enseignant, discipline):
        client.force_login(enseignant.user)
        reponse = client.post(
            reverse("elearning:enseignant_module_creer"),
            {
                "titre": "Herméneutique biblique",
                "description": "Lire le texte avec méthode.",
                "discipline": discipline.pk,
                "niveau": ModuleFormation.Niveau.INITIATION,
                "ects": "2.5",
                "seuil_completion": 80,
            },
        )
        assert reponse.status_code == 302
        module = ModuleFormation.objects.get(titre="Herméneutique biblique")
        assert module.responsable == enseignant
        assert module.slug == "hermeneutique-biblique"
        assert module.statut == ModuleFormation.StatutPublication.BROUILLON

    def test_les_titres_identiques_donnent_des_adresses_distinctes(self, client, enseignant, discipline, module):
        client.force_login(enseignant.user)
        client.post(
            reverse("elearning:enseignant_module_creer"),
            {
                "titre": module.titre,
                "discipline": discipline.pk,
                "niveau": ModuleFormation.Niveau.INITIATION,
                "ects": "0",
                "seuil_completion": 80,
            },
        )
        assert ModuleFormation.objects.filter(titre=module.titre).count() == 2
        assert ModuleFormation.objects.filter(slug=f"{module.slug}-2").exists()

    def test_ajout_d_un_chapitre(self, client, enseignant, module):
        client.force_login(enseignant.user)
        client.post(
            reverse("elearning:enseignant_chapitre_creer", kwargs={"slug": module.slug}),
            {"titre": "Premiers principes", "ordre": 0},
        )
        chapitre = Chapitre.objects.get(module=module, titre="Premiers principes")
        assert chapitre.ordre == 1  # renseigné automatiquement

    def test_ordre_automatique_du_chapitre_utilise_la_plus_grande_position(self, client, enseignant, module):
        Chapitre.objects.create(module=module, titre="Premier", ordre=1)
        Chapitre.objects.create(module=module, titre="Troisième", ordre=3)
        client.force_login(enseignant.user)

        reponse = client.post(
            reverse("elearning:enseignant_chapitre_creer", kwargs={"slug": module.slug}),
            {"titre": "À la fin", "ordre": 0},
        )

        assert reponse.status_code == 302
        assert Chapitre.objects.get(module=module, titre="À la fin").ordre == 4

    def test_ajout_d_une_lecon_video(self, client, enseignant, chapitre, video_prete):
        video_prete.uploade_par = enseignant.user
        video_prete.save(update_fields=["uploade_par"])
        client.force_login(enseignant.user)

        client.post(
            reverse("elearning:enseignant_lecon_creer", kwargs={"chapitre_pk": chapitre.pk}),
            {
                "titre": "Le contexte historique",
                "type_lecon": Lecon.TypeLecon.VIDEO,
                "ordre": 0,
                "video": video_prete.pk,
                "duree_secondes": 600,
                "obligatoire": "on",
            },
        )
        assert Lecon.objects.filter(chapitre=chapitre, titre="Le contexte historique").exists()

    def test_la_page_de_modification_recoit_le_chapitre(self, client, enseignant, lecon):
        client.force_login(enseignant.user)

        reponse = client.get(reverse("elearning:enseignant_lecon_modifier", kwargs={"pk": lecon.pk}))

        assert reponse.status_code == 200
        assert reponse.context["chapitre"] == lecon.chapitre
        assert (
            reverse(
                "elearning:enseignant_structure",
                kwargs={"slug": lecon.chapitre.module.slug},
            )
            in reponse.content.decode()
        )

    def test_ordre_automatique_de_la_lecon_utilise_la_plus_grande_position(self, client, enseignant, chapitre, lecon):
        Lecon.objects.create(
            chapitre=chapitre,
            titre="Troisième",
            slug="troisieme",
            type_lecon=Lecon.TypeLecon.TEXTE,
            ordre=3,
        )
        client.force_login(enseignant.user)

        reponse = client.post(
            reverse("elearning:enseignant_lecon_creer", kwargs={"chapitre_pk": chapitre.pk}),
            {
                "titre": "À la fin",
                "type_lecon": Lecon.TypeLecon.TEXTE,
                "ordre": 0,
                "contenu_texte": "Contenu",
            },
        )

        assert reponse.status_code == 302
        assert Lecon.objects.get(chapitre=chapitre, titre="À la fin").ordre == 4

    def test_une_position_de_lecon_deja_utilisee_affiche_une_erreur(self, client, enseignant, chapitre, lecon):
        client.force_login(enseignant.user)
        reponse = client.post(
            reverse("elearning:enseignant_lecon_creer", kwargs={"chapitre_pk": chapitre.pk}),
            {
                "titre": "Position en double",
                "type_lecon": Lecon.TypeLecon.TEXTE,
                "ordre": lecon.ordre,
            },
        )

        assert reponse.status_code == 200
        assert "position est déjà utilisée" in reponse.content.decode()
        assert not Lecon.objects.filter(chapitre=chapitre, titre="Position en double").exists()

    def test_deux_titres_de_lecon_identiques_recoivent_des_slugs_distincts(self, client, enseignant, chapitre, lecon):
        premiere = Lecon.objects.create(
            chapitre=chapitre,
            titre="Titre identique",
            slug="titre-identique",
            type_lecon=Lecon.TypeLecon.TEXTE,
            ordre=3,
        )
        client.force_login(enseignant.user)
        reponse = client.post(
            reverse("elearning:enseignant_lecon_creer", kwargs={"chapitre_pk": chapitre.pk}),
            {
                "titre": premiere.titre,
                "type_lecon": Lecon.TypeLecon.TEXTE,
                "ordre": 0,
            },
        )

        assert reponse.status_code == 302
        assert Lecon.objects.filter(chapitre=chapitre, slug=f"{premiere.slug}-2").exists()

    def test_youtube_est_utilisable_sur_un_module_protege_uniquement_en_dev(
        self, client, enseignant, chapitre, settings
    ):
        settings.DEBUG = True
        settings.ELEARNING_AUTORISER_VIDEO_PUBLIQUE_EN_DEV = True
        video = VideoAsset.objects.create(
            titre="Essai YouTube",
            cle_stockage="dQw4w9WgXcQ",
            fournisseur="youtube",
            statut_traitement=VideoAsset.StatutTraitement.PRET,
            uploade_par=enseignant.user,
        )
        client.force_login(enseignant.user)

        reponse = client.post(
            reverse("elearning:enseignant_lecon_creer", kwargs={"chapitre_pk": chapitre.pk}),
            {
                "titre": "Essai YouTube",
                "type_lecon": Lecon.TypeLecon.VIDEO,
                "ordre": 0,
                "video": video.pk,
            },
        )

        assert reponse.status_code == 302
        assert Lecon.objects.filter(chapitre=chapitre, video=video).exists()

    def test_youtube_reste_refuse_sur_un_module_protege_hors_dev(self, client, enseignant, chapitre, settings):
        settings.DEBUG = False
        settings.ELEARNING_AUTORISER_VIDEO_PUBLIQUE_EN_DEV = True
        video = VideoAsset.objects.create(
            titre="YouTube interdit",
            cle_stockage="abcdefghijk",
            fournisseur="youtube",
            statut_traitement=VideoAsset.StatutTraitement.PRET,
            uploade_par=enseignant.user,
        )
        client.force_login(enseignant.user)

        reponse = client.post(
            reverse("elearning:enseignant_lecon_creer", kwargs={"chapitre_pk": chapitre.pk}),
            {
                "titre": "YouTube interdit",
                "type_lecon": Lecon.TypeLecon.VIDEO,
                "ordre": 0,
                "video": video.pk,
            },
        )

        assert reponse.status_code == 200
        assert "ne protège pas assez" in reponse.content.decode()
        assert not Lecon.objects.filter(chapitre=chapitre, video=video).exists()

    def test_une_lecon_video_sans_fichier_est_refusee(self, client, enseignant, chapitre):
        client.force_login(enseignant.user)
        reponse = client.post(
            reverse("elearning:enseignant_lecon_creer", kwargs={"chapitre_pk": chapitre.pk}),
            {"titre": "Sans vidéo", "type_lecon": Lecon.TypeLecon.VIDEO, "ordre": 1},
        )
        assert reponse.status_code == 200
        assert b"doit r" in reponse.content  # « doit référencer un fichier »
        assert not Lecon.objects.filter(titre="Sans vidéo").exists()

    def test_je_ne_peux_rattacher_que_mes_propres_videos(
        self, client, enseignant, autre_enseignant, chapitre, video_prete
    ):
        video_prete.uploade_par = autre_enseignant.user
        video_prete.save(update_fields=["uploade_par"])
        client.force_login(enseignant.user)

        reponse = client.post(
            reverse("elearning:enseignant_lecon_creer", kwargs={"chapitre_pk": chapitre.pk}),
            {"titre": "Vidéo d'un autre", "type_lecon": Lecon.TypeLecon.VIDEO, "ordre": 1, "video": video_prete.pk},
        )
        assert reponse.status_code == 200
        assert not Lecon.objects.filter(titre="Vidéo d'un autre").exists()


@pytest.mark.django_db
class TestPublicationControlee:
    def test_un_module_sans_lecon_ne_se_publie_pas(self, client, enseignant, discipline):
        module = ModuleFormation.objects.create(
            titre="Vide", slug="vide", discipline=discipline, responsable=enseignant
        )
        client.force_login(enseignant.user)
        client.post(reverse("elearning:enseignant_publier", kwargs={"slug": module.slug}))
        module.refresh_from_db()
        assert module.statut == ModuleFormation.StatutPublication.BROUILLON

    def test_une_video_non_prete_bloque_la_publication(self, client, enseignant, module, lecon, video_prete):
        module.statut = ModuleFormation.StatutPublication.BROUILLON
        module.save(update_fields=["statut"])
        video_prete.statut_traitement = VideoAsset.StatutTraitement.EN_COURS
        video_prete.save(update_fields=["statut_traitement"])

        client.force_login(enseignant.user)
        reponse = client.post(reverse("elearning:enseignant_publier", kwargs={"slug": module.slug}), follow=True)
        module.refresh_from_db()
        assert module.statut == ModuleFormation.StatutPublication.BROUILLON
        assert "préparation" in reponse.content.decode()

    def test_un_module_complet_se_publie(self, client, enseignant, module, lecon):
        module.statut = ModuleFormation.StatutPublication.BROUILLON
        module.save(update_fields=["statut"])
        client.force_login(enseignant.user)

        client.post(reverse("elearning:enseignant_publier", kwargs={"slug": module.slug}))
        module.refresh_from_db()
        assert module.statut == ModuleFormation.StatutPublication.PUBLIE
        assert module.date_publication is not None

    def test_depublication(self, client, enseignant, module, lecon):
        client.force_login(enseignant.user)
        client.post(reverse("elearning:enseignant_depublier", kwargs={"slug": module.slug}))
        module.refresh_from_db()
        assert module.statut == ModuleFormation.StatutPublication.BROUILLON


@pytest.mark.django_db
class TestBibliothequeVideo:
    def test_un_fichier_video_n_est_jamais_accepte(self, client, enseignant, tmp_path, settings):
        settings.MEDIA_ROOT = tmp_path
        client.force_login(enseignant.user)
        reponse = client.post(
            reverse("elearning:enseignant_videos"),
            {
                "titre": "Séance 1",
                "fichier": SimpleUploadedFile("cours.mp4", b"video", content_type="video/mp4"),
            },
        )
        assert reponse.status_code == 200
        assert VideoAsset.objects.count() == 0
        assert list(tmp_path.rglob("*")) == []

    def test_une_video_utilisee_ne_se_supprime_pas(self, client, enseignant, lecon, video_prete):
        video_prete.uploade_par = enseignant.user
        video_prete.save(update_fields=["uploade_par"])
        client.force_login(enseignant.user)

        client.post(reverse("elearning:enseignant_video_supprimer", kwargs={"pk": video_prete.pk}))
        assert VideoAsset.objects.filter(pk=video_prete.pk).exists()

    def test_je_ne_supprime_pas_la_video_d_un_autre(self, client, enseignant, autre_enseignant, video_prete):
        video_prete.uploade_par = autre_enseignant.user
        video_prete.save(update_fields=["uploade_par"])
        client.force_login(enseignant.user)
        assert (
            client.post(reverse("elearning:enseignant_video_supprimer", kwargs={"pk": video_prete.pk})).status_code
            == 404
        )


@pytest.mark.django_db
class TestSousTitres:
    def test_ajout_d_une_piste_vtt(self, client, enseignant, video_prete, tmp_path, settings):
        settings.MEDIA_ROOT = tmp_path
        video_prete.uploade_par = enseignant.user
        video_prete.save(update_fields=["uploade_par"])
        client.force_login(enseignant.user)

        client.post(
            reverse("elearning:enseignant_soustitre", kwargs={"video_pk": video_prete.pk}),
            {
                "langue": "fr",
                "libelle": "Français",
                "fichier_vtt": SimpleUploadedFile("st.vtt", b"WEBVTT\n\n00:00.000 --> 00:02.000\nBonjour"),
                "par_defaut": "on",
            },
        )
        assert SousTitre.objects.filter(video=video_prete, langue="fr").exists()

    def test_un_fichier_qui_n_est_pas_du_vtt_est_refuse(self, client, enseignant, video_prete, tmp_path, settings):
        settings.MEDIA_ROOT = tmp_path
        video_prete.uploade_par = enseignant.user
        video_prete.save(update_fields=["uploade_par"])
        client.force_login(enseignant.user)

        reponse = client.post(
            reverse("elearning:enseignant_soustitre", kwargs={"video_pk": video_prete.pk}),
            {"langue": "fr", "libelle": "Français", "fichier_vtt": SimpleUploadedFile("st.vtt", b"pas du vtt")},
        )
        assert reponse.status_code == 200
        assert SousTitre.objects.count() == 0


@pytest.mark.django_db
class TestReordonnancement:
    def test_l_ordre_est_persiste(self, client, enseignant, chapitre, lecon, lecon_apercu):
        client.force_login(enseignant.user)
        client.post(
            reverse("elearning:enseignant_lecons_ordonner", kwargs={"chapitre_pk": chapitre.pk}),
            {"lecon": [str(lecon_apercu.pk), str(lecon.pk)]},
        )
        lecon.refresh_from_db()
        lecon_apercu.refresh_from_db()
        assert lecon_apercu.ordre == 1
        assert lecon.ordre == 2

    def test_l_inversion_ne_heurte_pas_la_contrainte_d_unicite(self, client, enseignant, chapitre, lecon, lecon_apercu):
        """Deux leçons ne peuvent pas porter le même rang, même transitoirement."""
        client.force_login(enseignant.user)
        for ordre in ([lecon_apercu.pk, lecon.pk], [lecon.pk, lecon_apercu.pk]):
            reponse = client.post(
                reverse("elearning:enseignant_lecons_ordonner", kwargs={"chapitre_pk": chapitre.pk}),
                {"lecon": [str(pk) for pk in ordre]},
            )
            assert reponse.status_code == 302


@pytest.mark.django_db
class TestAudience:
    def test_la_page_expose_les_taux_par_lecon(self, client, enseignant, module, lecon, acces):
        client.force_login(enseignant.user)
        reponse = client.get(reverse("elearning:enseignant_audience", kwargs={"slug": module.slug}))
        assert reponse.status_code == 200
        contenu = reponse.content.decode()
        assert lecon.titre in contenu
        assert reponse.context["total_inscrits"] == 1
        assert reponse.context["jamais_commence"] == 1

    def test_l_audience_d_un_autre_est_inaccessible(self, client, autre_enseignant, module):
        client.force_login(autre_enseignant.user)
        assert client.get(reverse("elearning:enseignant_audience", kwargs={"slug": module.slug})).status_code == 404


@pytest.mark.django_db
class TestReferencementVideoExterne:
    """
    L'enseignant colle une URL externe. Le média ne transite jamais par notre
    stockage et la restriction de propriété reste appliquée.
    """

    @pytest.fixture(autouse=True)
    def _fournisseur_externe(self, settings):
        settings.ELEARNING_DIFFUSION_VIDEO = "bunny"
        settings.BUNNY_ZONE_DIFFUSION = "https://iteag.b-cdn.net"
        settings.BUNNY_CLE_SIGNATURE = "cle-de-test"

    def test_la_page_propose_le_referencement(self, client, enseignant):
        client.force_login(enseignant.user)
        reponse = client.get(reverse("elearning:enseignant_videos"))
        assert reponse.status_code == 200
        assert "Référencer" in reponse.content.decode()
        assert "Aucun fichier n&#x27;est chargé" in reponse.content.decode()

    def test_un_lien_bunny_cree_la_video(self, client, enseignant):
        client.force_login(enseignant.user)
        client.post(
            reverse("elearning:enseignant_videos"),
            {
                "titre": "Introduction",
                "adresse_video": "https://iframe.mediadelivery.net/embed/1234/8f2c1e94abcd",
                "transcription": "",
            },
        )
        video = VideoAsset.objects.get(titre="Introduction")
        assert video.cle_stockage == "8f2c1e94abcd"
        assert video.fournisseur == "bunny"
        assert video.statut_traitement == VideoAsset.StatutTraitement.PRET

    def test_une_adresse_youtube_est_detectee(self, client, enseignant):
        client.force_login(enseignant.user)
        client.post(
            reverse("elearning:enseignant_videos"),
            {
                "titre": "Bande-annonce",
                "adresse_video": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            },
        )
        video = VideoAsset.objects.get(titre="Bande-annonce")
        assert video.cle_stockage == "dQw4w9WgXcQ"
        assert video.fournisseur == "youtube"

    def test_une_adresse_vimeo_est_detectee(self, client, enseignant):
        client.force_login(enseignant.user)
        client.post(
            reverse("elearning:enseignant_videos"),
            {"titre": "Extrait", "adresse_video": "https://vimeo.com/123456789"},
        )
        video = VideoAsset.objects.get(titre="Extrait")
        assert video.cle_stockage == "123456789"
        assert video.fournisseur == "vimeo"

    @pytest.mark.parametrize(
        "adresse",
        [
            "id-seul-sans-lien",
            "http://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "https://videos.example.org/abcdef123456",
        ],
    )
    def test_un_lien_non_securise_ou_inconnu_est_refuse(self, client, enseignant, adresse):
        client.force_login(enseignant.user)
        reponse = client.post(
            reverse("elearning:enseignant_videos"),
            {"titre": "Cassée", "adresse_video": adresse},
        )
        assert reponse.status_code == 200
        assert not VideoAsset.objects.filter(titre="Cassée").exists()

    def test_un_lien_deja_reference_est_refuse(self, client, enseignant):
        VideoAsset.objects.create(titre="Déjà là", cle_stockage="dQw4w9WgXcQ", fournisseur="youtube")
        client.force_login(enseignant.user)
        client.post(
            reverse("elearning:enseignant_videos"),
            {
                "titre": "Doublon",
                "adresse_video": "https://youtu.be/dQw4w9WgXcQ",
            },
        )
        assert not VideoAsset.objects.filter(titre="Doublon").exists()

    def test_un_etudiant_ne_reference_rien(self, client, utilisateur_etudiant):
        client.force_login(utilisateur_etudiant)
        reponse = client.post(
            reverse("elearning:enseignant_videos"),
            {
                "titre": "Intrusion",
                "adresse_video": "https://youtu.be/dQw4w9WgXcQ",
            },
        )
        assert reponse.status_code in (302, 403)
        assert not VideoAsset.objects.filter(titre="Intrusion").exists()
