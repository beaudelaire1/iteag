"""
Tests des tâches asynchrones de la formation vidéo.

Ce sont elles qui tournent en production, hors de toute requête, et dont la
panne est silencieuse : personne ne voit une tâche échouer, on constate
seulement que rien n'avance. Le manuel d'exploitation en fait d'ailleurs son
premier incident — « les vidéos restent en préparation ».

Deux exigences guident ces tests. Une tâche ne doit jamais laisser un objet
dans un état intermédiaire : en cas d'échec, le statut doit dire « erreur » et
porter le motif, pas rester bloqué sur « en préparation ». Et l'absence d'un
outil facultatif — ffprobe, WeasyPrint — ne doit pas empêcher le travail
d'aboutir.
"""

from unittest import mock

import pytest

from apps.core.models import Notification
from apps.elearning.models import AttestationModule, Chapitre, Lecon, ModuleFormation, VideoAsset
from apps.elearning.tasks import expirer_acces, generer_attestation_pdf, preparer_video


@pytest.fixture
def video(db, enseignant):
    return VideoAsset.objects.create(
        titre="Séance d'ouverture",
        cle_stockage="videos/seance-ouverture.mp4",
        fournisseur="local",
        duree_secondes=0,
        uploade_par=enseignant.user,
        statut_traitement=VideoAsset.StatutTraitement.EN_ATTENTE,
    )


@pytest.mark.django_db
class TestPreparationVideo:
    def test_une_video_inconnue_ne_leve_pas(self):
        """Une tâche qui lève est rejouée indéfiniment par le courtier."""
        import uuid

        assert preparer_video(str(uuid.uuid4())) == "introuvable"

    def test_la_video_devient_prete(self, video):
        with mock.patch("apps.elearning.tasks._duree_secondes", return_value=1830):
            assert preparer_video(str(video.pk)) == "pret"
        video.refresh_from_db()
        assert video.statut_traitement == VideoAsset.StatutTraitement.PRET
        assert video.duree_secondes == 1830
        assert video.message_erreur == ""

    def test_l_absence_de_duree_ne_bloque_pas_la_publication(self, video):
        """ffprobe peut manquer de l'image : la durée reste celle saisie."""
        video.duree_secondes = 900
        video.save(update_fields=["duree_secondes"])

        with mock.patch("apps.elearning.tasks._duree_secondes", return_value=0):
            assert preparer_video(str(video.pk)) == "pret"

        video.refresh_from_db()
        assert video.statut_traitement == VideoAsset.StatutTraitement.PRET
        assert video.duree_secondes == 900

    def test_un_echec_laisse_un_statut_explicite(self, video):
        """
        Le pire état serait « en préparation » indéfiniment : l'exploitant ne
        saurait pas s'il faut attendre ou intervenir.
        """
        with mock.patch(
            "apps.elearning.tasks._duree_secondes", side_effect=FileNotFoundError("Fichier absent : videos/x.mp4")
        ):
            assert preparer_video(str(video.pk)) == "erreur"

        video.refresh_from_db()
        assert video.statut_traitement == VideoAsset.StatutTraitement.ERREUR
        assert "Fichier absent" in video.message_erreur

    def test_le_message_d_erreur_est_borne(self, video):
        """Le champ fait 500 caractères : un message plus long tronquerait à l'insertion."""
        with mock.patch("apps.elearning.tasks._duree_secondes", side_effect=RuntimeError("x" * 2000)):
            preparer_video(str(video.pk))
        video.refresh_from_db()
        assert len(video.message_erreur) <= 500

    def test_la_duree_du_module_est_recalculee(self, video, discipline, enseignant):
        """La durée annoncée au catalogue vient des leçons, pas d'une saisie."""
        module = ModuleFormation.objects.create(
            titre="Module tâche", slug="module-tache", discipline=discipline, responsable=enseignant
        )
        chapitre = Chapitre.objects.create(module=module, titre="Chapitre", ordre=1)
        Lecon.objects.create(
            chapitre=chapitre,
            titre="Leçon",
            slug="lecon-tache",
            ordre=1,
            type_lecon=Lecon.TypeLecon.VIDEO,
            video=video,
            duree_secondes=0,
        )

        with mock.patch("apps.elearning.tasks._duree_secondes", return_value=1200):
            preparer_video(str(video.pk))

        module.refresh_from_db()
        assert module.duree_totale_secondes == 1200

    def test_le_depositaire_est_prevenu(self, video, enseignant):
        with mock.patch("apps.elearning.tasks._duree_secondes", return_value=600):
            preparer_video(str(video.pk))
        assert Notification.objects.filter(destinataire=enseignant.user, titre__contains="Séance d'ouverture").exists()

    def test_une_video_sans_depositaire_ne_plante_pas(self, video):
        """Le compte de l'enseignant peut avoir été supprimé entre-temps."""
        video.uploade_par = None
        video.save(update_fields=["uploade_par"])
        with mock.patch("apps.elearning.tasks._duree_secondes", return_value=600):
            assert preparer_video(str(video.pk)) == "pret"


@pytest.mark.django_db
class TestLectureDeLaDuree:
    """`_duree_secondes` ne doit jamais faire échouer la préparation."""

    def test_un_fournisseur_externe_ne_lit_aucun_fichier(self, video, settings):
        """La vidéo est chez le fournisseur : rien à sonder de notre côté."""
        from apps.elearning.tasks import _duree_secondes

        settings.ELEARNING_DIFFUSION_VIDEO = "bunny"
        settings.BUNNY_ZONE_DIFFUSION = "https://iteag.b-cdn.net"
        settings.BUNNY_CLE_SIGNATURE = "cle"
        assert _duree_secondes(video) == 0

    def test_un_fichier_absent_est_signale(self, video, settings, tmp_path):
        from apps.elearning.tasks import _duree_secondes

        settings.MEDIA_ROOT = tmp_path
        settings.ELEARNING_DIFFUSION_VIDEO = "local"
        with pytest.raises(FileNotFoundError):
            _duree_secondes(video)

    def test_ffprobe_absent_laisse_la_duree_a_zero(self, video, settings, tmp_path):
        """L'outil n'est pas garanti présent dans l'image : ce n'est pas bloquant."""
        from django.core.files.base import ContentFile
        from django.core.files.storage import default_storage

        from apps.elearning.tasks import _duree_secondes

        settings.MEDIA_ROOT = tmp_path
        settings.ELEARNING_DIFFUSION_VIDEO = "local"
        default_storage.save(video.cle_stockage, ContentFile(b"\x00\x00\x00\x18ftypmp42"))

        with mock.patch("subprocess.run", side_effect=FileNotFoundError("ffprobe")):
            assert _duree_secondes(video) == 0


@pytest.mark.django_db
class TestExpirationDesAcces:
    def test_la_tache_retourne_le_nombre_traite(self):
        assert expirer_acces() == 0


@pytest.mark.django_db
class TestAttestation:
    @pytest.fixture
    def attestation(self, db, acces):
        return AttestationModule.objects.create(inscription=acces, numero="ITEAG-MOD-2026-00001")

    def test_une_attestation_inconnue_ne_leve_pas(self):
        import uuid

        assert generer_attestation_pdf(str(uuid.uuid4())) == "introuvable"

    def test_une_attestation_deja_produite_n_est_pas_refaite(self, attestation):
        """Rejouer la tâche ne doit pas remplacer un document déjà délivré."""
        from django.core.files.base import ContentFile

        attestation.fichier_pdf.save("deja.pdf", ContentFile(b"%PDF-1.7"), save=True)
        assert generer_attestation_pdf(str(attestation.pk)) == "deja_generee"

    def test_l_absence_de_weasyprint_est_traitee(self, attestation):
        """Sans le moteur PDF, l'attestation reste valable — seul le fichier manque."""
        with mock.patch.dict("sys.modules", {"weasyprint": None}):
            resultat = generer_attestation_pdf(str(attestation.pk))
        assert resultat in ("sans_pdf", "genere")
