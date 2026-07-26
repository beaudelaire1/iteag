"""
Tests des vues de lecture — la surface de sécurité du domaine.

Ce qui est vérifié ici n'est pas l'affichage mais l'invariant d'ADR-001 :
aucune adresse de fichier ne sort dans le HTML, et le droit est revérifié à
chaque demande de lecture.
"""

import json

import pytest
from django.urls import reverse

from apps.elearning.models import InscriptionModule, JournalAccesVideo, ProgressionLecon


@pytest.fixture(autouse=True)
def _cache_propre():
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()


def url_lecon(lecon):
    return reverse(
        "elearning:lecon_detail",
        kwargs={"slug": lecon.chapitre.module.slug, "lecon_slug": lecon.slug},
    )


def url_lecture(lecon):
    return reverse(
        "elearning:lecon_playback",
        kwargs={"slug": lecon.chapitre.module.slug, "lecon_slug": lecon.slug},
    )


def url_progression(lecon):
    return reverse(
        "elearning:lecon_progression",
        kwargs={"slug": lecon.chapitre.module.slug, "lecon_slug": lecon.slug},
    )


@pytest.mark.django_db
class TestPageDeLecon:
    def test_un_ayant_droit_accede(self, client, utilisateur_etudiant, lecon, acces):
        client.force_login(utilisateur_etudiant)
        assert client.get(url_lecon(lecon)).status_code == 200

    def test_aucune_adresse_de_fichier_dans_le_html(self, client, utilisateur_etudiant, lecon, acces, video_prete):
        """L'invariant central : la page ne doit rien révéler du stockage."""
        client.force_login(utilisateur_etudiant)
        contenu = client.get(url_lecon(lecon)).content.decode()
        assert video_prete.cle_stockage not in contenu
        assert ".mp4" not in contenu

    def test_sans_droit_la_page_explique_le_refus(self, client, utilisateur_etudiant, lecon, profil):
        client.force_login(utilisateur_etudiant)
        reponse = client.get(url_lecon(lecon))
        assert reponse.status_code == 403
        assert "secrétariat" in reponse.content.decode().lower()

    def test_un_refus_est_journalise(self, client, utilisateur_etudiant, lecon, profil):
        client.force_login(utilisateur_etudiant)
        client.get(url_lecon(lecon))
        assert JournalAccesVideo.objects.filter(resultat=JournalAccesVideo.Resultat.REFUSE_DROIT).exists()

    def test_l_apercu_est_ouvert_a_un_visiteur(self, client, lecon_apercu):
        assert client.get(url_lecon(lecon_apercu)).status_code == 200


@pytest.mark.django_db
class TestDelivranceDeLAdresse:
    def test_un_ayant_droit_obtient_une_adresse_ephemere(self, client, utilisateur_etudiant, lecon, acces):
        client.force_login(utilisateur_etudiant)
        reponse = client.post(url_lecture(lecon))
        assert reponse.status_code == 200
        charge = reponse.json()
        assert charge["url"]
        assert charge["expire_dans"] == 300

    def test_sans_droit_l_adresse_est_refusee(self, client, utilisateur_etudiant, lecon, profil):
        client.force_login(utilisateur_etudiant)
        assert client.post(url_lecture(lecon)).status_code == 403

    def test_une_revocation_prend_effet_immediatement(self, client, utilisateur_etudiant, lecon, acces):
        """La page a pu être servie avant la révocation : le droit est revérifié."""
        client.force_login(utilisateur_etudiant)
        assert client.post(url_lecture(lecon)).status_code == 200

        acces.statut = InscriptionModule.StatutAcces.REVOQUE
        acces.save(update_fields=["statut"])
        assert client.post(url_lecture(lecon)).status_code == 403

    def test_une_seconde_lecture_ailleurs_donne_429(self, client, utilisateur_etudiant, lecon, acces):
        from django.test import Client

        client.force_login(utilisateur_etudiant)
        assert client.post(url_lecture(lecon)).status_code == 200

        autre_appareil = Client()
        autre_appareil.force_login(utilisateur_etudiant)
        reponse = autre_appareil.post(url_lecture(lecon))
        assert reponse.status_code == 429
        assert reponse.json()["motif"] == JournalAccesVideo.Resultat.REFUSE_QUOTA

    def test_une_video_non_prete_est_signalee(self, client, utilisateur_etudiant, lecon, acces, video_prete):
        from apps.elearning.models import VideoAsset

        video_prete.statut_traitement = VideoAsset.StatutTraitement.EN_COURS
        video_prete.save(update_fields=["statut_traitement"])
        client.force_login(utilisateur_etudiant)
        assert client.post(url_lecture(lecon)).status_code == 409

    def test_la_methode_get_est_refusee(self, client, utilisateur_etudiant, lecon, acces):
        client.force_login(utilisateur_etudiant)
        assert client.get(url_lecture(lecon)).status_code == 405

    def test_chaque_delivrance_est_journalisee(self, client, utilisateur_etudiant, lecon, acces):
        client.force_login(utilisateur_etudiant)
        client.post(url_lecture(lecon))
        entree = JournalAccesVideo.objects.filter(resultat=JournalAccesVideo.Resultat.AUTORISE).first()
        assert entree is not None
        assert entree.ttl_accorde == 300


@pytest.mark.django_db
class TestServiceDuFichier:
    def test_un_jeton_valide_sert_le_fichier(self, client, utilisateur_etudiant, lecon, acces, tmp_path, settings):
        settings.MEDIA_ROOT = tmp_path
        from django.core.files.base import ContentFile
        from django.core.files.storage import default_storage

        default_storage.save(lecon.video.cle_stockage, ContentFile(b"contenu-video"))

        client.force_login(utilisateur_etudiant)
        adresse = client.post(url_lecture(lecon)).json()["url"]
        reponse = client.get(adresse)
        assert reponse.status_code == 200
        assert reponse["Accept-Ranges"] == "bytes"
        assert "no-store" in reponse["Cache-Control"]

    def test_un_jeton_falsifie_est_rejete(self, client):
        assert client.get(reverse("elearning:fichier_video", kwargs={"jeton": "n-importe-quoi"})).status_code == 404

    def test_un_jeton_expire_est_rejete(self, lecon):
        from apps.elearning.storage import LocalStockageVideo

        jeton = LocalStockageVideo().url_lecture(lecon.video.cle_stockage).rsplit("/", 2)[1]
        assert LocalStockageVideo.cle_depuis_jeton(jeton, ttl=-1) is None


@pytest.mark.django_db
class TestSignalDeProgression:
    def test_le_signal_enregistre_la_progression(self, client, utilisateur_etudiant, lecon, acces):
        client.force_login(utilisateur_etudiant)
        reponse = client.post(
            url_progression(lecon),
            data=json.dumps({"position": 60, "delta": 15}),
            content_type="application/json",
        )
        assert reponse.status_code == 200
        assert reponse.json()["pourcentage_lecon"] > 0
        assert ProgressionLecon.objects.filter(inscription=acces, lecon=lecon).exists()

    def test_un_increment_exagere_est_plafonne_cote_serveur(self, client, utilisateur_etudiant, lecon, acces):
        client.force_login(utilisateur_etudiant)
        client.post(
            url_progression(lecon),
            data=json.dumps({"position": 600, "delta": 100000}),
            content_type="application/json",
        )
        avancement = ProgressionLecon.objects.get(inscription=acces, lecon=lecon)
        assert avancement.temps_visionnage_cumule == 30
        assert avancement.termine is False

    def test_sans_droit_le_signal_est_refuse(self, client, utilisateur_etudiant, lecon, profil):
        client.force_login(utilisateur_etudiant)
        reponse = client.post(
            url_progression(lecon),
            data=json.dumps({"position": 60, "delta": 15}),
            content_type="application/json",
        )
        assert reponse.status_code == 403

    def test_une_charge_illisible_ne_plante_pas(self, client, utilisateur_etudiant, lecon, acces):
        client.force_login(utilisateur_etudiant)
        reponse = client.post(url_progression(lecon), data="pas du json", content_type="application/json")
        assert reponse.status_code == 200


@pytest.mark.django_db
class TestCatalogueEtFiches:
    def test_le_catalogue_liste_les_modules_publies(self, client, module):
        contenu = client.get(reverse("elearning:catalogue")).content.decode()
        assert module.titre in contenu

    def test_le_catalogue_masque_les_brouillons(self, client, module):
        from apps.elearning.models import ModuleFormation

        module.statut = ModuleFormation.StatutPublication.BROUILLON
        module.save(update_fields=["statut"])
        assert module.titre not in client.get(reverse("elearning:catalogue")).content.decode()

    def test_la_fiche_d_un_brouillon_donne_404(self, client, module):
        from apps.elearning.models import ModuleFormation

        module.statut = ModuleFormation.StatutPublication.BROUILLON
        module.save(update_fields=["statut"])
        assert client.get(module.get_absolute_url()).status_code == 404

    def test_mes_formations_liste_les_acces(self, client, utilisateur_etudiant, acces, module):
        client.force_login(utilisateur_etudiant)
        contenu = client.get(reverse("elearning:mes_formations")).content.decode()
        assert module.titre in contenu

    def test_mes_formations_exige_une_connexion(self, client):
        assert client.get(reverse("elearning:mes_formations")).status_code == 302


@pytest.mark.django_db
class TestAttestations:
    def test_la_verification_publique_trouve_l_attestation(self, client, acces, module):
        from apps.elearning.models import AttestationModule

        attestation = AttestationModule.objects.create(inscription=acces)
        reponse = client.get(reverse("elearning:verifier_attestation", kwargs={"code": attestation.code_verification}))
        assert reponse.status_code == 200
        assert attestation.numero in reponse.content.decode()

    def test_un_code_inconnu_donne_404(self, client):
        assert client.get(reverse("elearning:verifier_attestation", kwargs={"code": "code-invente"})).status_code == 404

    def test_on_ne_telecharge_pas_l_attestation_d_un_autre(self, client, acces, db, profil):
        from apps.accounts.models import User
        from apps.elearning.models import AttestationModule

        attestation = AttestationModule.objects.create(inscription=acces)
        intrus = User.objects.create_user(username="intrus", email="i@iteag.org", password="motdepasse-long-12")
        client.force_login(intrus)
        assert (
            client.get(reverse("elearning:attestation_telecharger", kwargs={"pk": attestation.pk})).status_code == 404
        )
