"""Les fichiers déposés doivent suivre le déploiement.

En développement ils vivent dans « src/media/ », sur le poste. En production le
stockage par défaut est Cloudflare R2, et la base ne retient qu'un chemin
relatif : après un déploiement, chaque image pointe vers un fichier que le
bucket n'a jamais reçu. L'écran affiche un cadre vide, sans qu'aucune erreur
ne soit levée — c'est ce silence qui rend le défaut coûteux à diagnostiquer.
"""

from io import StringIO

import pytest
from django.core.checks import Error
from django.core.files.storage import default_storage
from django.core.management import call_command
from django.test import override_settings

from apps.core.checks import configuration_stockage_media
from apps.formations.models import Professeur

pytestmark = pytest.mark.django_db


CHEMIN = "professeurs/portrait.jpg"
CONTENU = b"\xff\xd8\xff-image"


@pytest.fixture
def poste_local(tmp_path, settings):
    """Deux répertoires distincts, comme en vrai.

    Le poste de développement d'un côté, le stockage de destination de l'autre.
    Les confondre — ce que fait un test naïf, puisque « default_storage » lit
    MEDIA_ROOT en local — ne prouverait rien du tout.
    """
    poste = tmp_path / "poste"
    destination = tmp_path / "destination"
    (poste / "professeurs").mkdir(parents=True)
    (poste / CHEMIN).write_bytes(CONTENU)
    destination.mkdir()
    settings.MEDIA_ROOT = str(destination)
    return poste


@pytest.fixture
def professeur_avec_photo(db, poste_local):
    # La base ne retient qu'un chemin : le fichier, lui, n'est pas à destination.
    return Professeur.objects.create(nom="Nisus", prenom="Alain", slug="alain-nisus", photo=CHEMIN)


def _transferer(poste, *arguments):
    sortie, erreurs = StringIO(), StringIO()
    call_command("transferer_media", "--source", str(poste), *arguments, stdout=sortie, stderr=erreurs)
    return sortie.getvalue(), erreurs.getvalue()


class TestTransfertMedia:
    def test_l_inventaire_n_ecrit_rien(self, professeur_avec_photo, poste_local):
        """Sans « --executer », la commande dit ce qu'elle ferait et s'arrête."""
        sortie, _ = _transferer(poste_local)

        assert "1 fichier(s) à transférer" in sortie
        assert not default_storage.exists(CHEMIN)

    def test_le_transfert_televerse_le_fichier_manquant(self, professeur_avec_photo, poste_local):
        assert not default_storage.exists(CHEMIN)

        _transferer(poste_local, "--executer")

        assert default_storage.exists(CHEMIN)
        with default_storage.open(CHEMIN, "rb") as fichier:
            assert fichier.read() == CONTENU

    def test_le_chemin_exact_est_conserve(self, professeur_avec_photo, poste_local):
        """Un renommage à l'arrivée casserait le lien que la base référence."""
        _transferer(poste_local, "--executer")

        professeur_avec_photo.refresh_from_db()
        assert professeur_avec_photo.photo.name == CHEMIN
        assert default_storage.exists(CHEMIN)

    def test_relancer_ne_duplique_rien(self, professeur_avec_photo, poste_local):
        for _ in range(3):
            _transferer(poste_local, "--executer")

        sortie, _ = _transferer(poste_local)
        assert "0 fichier(s) à transférer" in sortie
        assert "1 déjà présent(s)" in sortie

    def test_un_fichier_absent_en_local_est_signale(self, professeur_avec_photo, poste_local):
        """Un cadre vide dont la cause n'est pas le transfert doit se voir aussi."""
        (poste_local / CHEMIN).unlink()

        sortie, erreurs = _transferer(poste_local)

        assert "manquant en local" in erreurs
        assert "introuvable" in sortie


class TestControleDuStockage:
    def test_le_stockage_objet_sans_identifiants_est_une_erreur(self):
        """Sans clés, le stockage S3 fabrique des URL que rien ne sert."""
        with override_settings(
            STORAGES={"default": {"BACKEND": "storages.backends.s3boto3.S3Boto3Storage"}},
            AWS_ACCESS_KEY_ID="",
            AWS_SECRET_ACCESS_KEY="",
            AWS_STORAGE_BUCKET_NAME="",
        ):
            problemes = configuration_stockage_media(None)

        assert problemes and isinstance(problemes[0], Error)
        assert problemes[0].id == "core.E005"
        assert "AWS_ACCESS_KEY_ID" in problemes[0].hint

    def test_le_stockage_local_ne_declenche_rien(self):
        with override_settings(
            STORAGES={"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"}},
        ):
            assert configuration_stockage_media(None) == []

    def test_un_stockage_objet_complet_passe(self):
        with override_settings(
            STORAGES={"default": {"BACKEND": "storages.backends.s3boto3.S3Boto3Storage"}},
            AWS_ACCESS_KEY_ID="cle",
            AWS_SECRET_ACCESS_KEY="secret",
            AWS_STORAGE_BUCKET_NAME="iteag-media",
            AWS_S3_ENDPOINT_URL="https://exemple.r2.cloudflarestorage.com",
        ):
            assert configuration_stockage_media(None) == []
