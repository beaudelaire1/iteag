"""Le cas où la signature est déposée mais illisible.

Le stockage des médias est distant : lire une signature est un appel réseau qui
peut échouer — panne du fournisseur, objet supprimé, droits retirés. Ce chemin
n'était couvert par aucun test, et le code le confondait avec « aucune signature
déposée » : le PDF sortait quand même, avec la date, le nom et la qualité du
signataire, mais sans sa signature. Un document qui a l'air signé et ne l'est
pas est pire qu'un document manquant.
"""

from unittest import mock

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.accounts.models import User
from apps.documents.models import DocumentAdministratif, SuiviGenerationPDF
from apps.documents.services_generation import (
    SignatureIllisible,
    _user_signature_uri,
    obtenir_signature_secretariat_data_uri,
)

PNG_MINIMAL = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
    b"\x1f\x15c4\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff?"
    b'\x03\x00\x05\xfe\x02\xfe\xa7\x9a\x9c"\x00\x00\x00\x00'
    b"IEND\xaeB`\x82"
)


@pytest.fixture
def secretaire(db, tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    return User.objects.create_user(
        username="secretaire_signature",
        email="secretaire.signature@iteag.org",
        password="motdepasse-long-12",
        first_name="Jeanne",
        last_name="Bertrand",
        role=User.Role.SECRETARIAT,
        signature=SimpleUploadedFile("signature.png", PNG_MINIMAL, content_type="image/png"),
    )


@pytest.mark.django_db
class TestUneSignatureAbsenteResteUneDegradationAcceptee:
    def test_aucun_utilisateur(self):
        assert _user_signature_uri(None) == ""

    def test_utilisateur_sans_signature(self):
        compte = User.objects.create_user(
            username="sans_signature",
            email="sans.signature@iteag.org",
            password="motdepasse-long-12",
            role=User.Role.SECRETARIAT,
        )
        assert _user_signature_uri(compte) == ""

    def test_personne_n_a_depose_de_signature(self):
        assert obtenir_signature_secretariat_data_uri() == ("", "", "")


@pytest.mark.django_db
class TestUneSignatureIllisibleRefuseDeSeTaire:
    def test_la_lecture_en_echec_leve_une_erreur_explicite(self, secretaire):
        with mock.patch.object(
            type(secretaire.signature),
            "open",
            side_effect=OSError("R2 indisponible"),
        ):
            with pytest.raises(SignatureIllisible):
                _user_signature_uri(secretaire)

    def test_la_signature_du_secretariat_propage_l_erreur(self, secretaire):
        """Le document administratif ne doit pas se rabattre sur « pas de signature »."""
        with mock.patch(
            "apps.documents.services_generation._user_signature_uri",
            side_effect=SignatureIllisible("R2 indisponible"),
        ):
            with pytest.raises(SignatureIllisible):
                obtenir_signature_secretariat_data_uri()

    def test_l_echec_est_journalise(self, secretaire, caplog):
        with mock.patch.object(
            type(secretaire.signature),
            "open",
            side_effect=OSError("R2 indisponible"),
        ):
            with pytest.raises(SignatureIllisible):
                _user_signature_uri(secretaire)

        assert any("Signature illisible" in enregistrement.message for enregistrement in caplog.records)

    def test_une_signature_lisible_reste_lisible(self, secretaire):
        uri = _user_signature_uri(secretaire)
        assert uri.startswith("data:image/png;base64,")


@pytest.mark.django_db
class TestLaGenerationEchoueAuLieuDeLivrerUnePieceNonSignee:
    def test_le_document_passe_en_echec_avec_un_message(self, db):
        from apps.documents.tasks import _executer

        etudiant = User.objects.create_user(
            username="etudiant_signature",
            email="etudiant.signature@iteag.org",
            password="motdepasse-long-12",
            role=User.Role.ETUDIANT,
        )
        document = DocumentAdministratif.objects.create(
            etudiant=etudiant,
            type_document=DocumentAdministratif.TypeDocument.ATTESTATION,
        )

        def fabriquer(_document):
            raise SignatureIllisible("R2 indisponible")

        resultat = _executer(
            DocumentAdministratif,
            document.pk,
            document.jeton_generation,
            fabriquer,
        )

        document.refresh_from_db()
        assert resultat == "echec"
        assert document.statut_generation == SuiviGenerationPDF.StatutGeneration.ECHEC
        assert document.erreur_generation
        assert not document.fichier_pdf
        # Le message est celui que lira l'étudiant : il doit inviter à réessayer,
        # pas exposer la panne du stockage.
        assert "Réessayez" in document.erreur_generation
