"""
Tests des documents administratifs de l'étudiant.

Un relevé de notes ou une attestation porte des données personnelles : le point
sensible est qu'un étudiant ne puisse récupérer que les siens.
"""

from unittest.mock import patch

import pytest
from django.test import override_settings
from django.urls import reverse

from apps.academics.models import (
    CoursDeSession,
    CreditECTS,
    ProfilEtudiant,
    Promotion,
    SessionAcademique,
)
from apps.accounts.models import User
from apps.documents.models import DocumentAdministratif
from apps.formations.models import Cours, Discipline, Parcours, Professeur
from apps.lms.models import Evaluation


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


def _cours_de_session(etudiant: ProfilEtudiant) -> CoursDeSession:
    """Un cours réellement programmé — ce que le relevé imprime ligne à ligne."""
    discipline = Discipline.objects.create(nom="Exégèse", slug="exegese-doc")
    cours = Cours.objects.create(titre="Exégèse de Romains", slug="exegese-romains-doc", discipline=discipline)
    utilisateur = User.objects.create_user(
        username="prof_doc", email="prof_doc@iteag.org", password="motdepasse-long-12", role=User.Role.ENSEIGNANT
    )
    professeur = Professeur.objects.create(user=utilisateur, nom="Duval", prenom="Anne", slug="anne-duval-doc")
    session = SessionAcademique.objects.create(
        nom="Session de Pâques",
        periode=SessionAcademique.Periode.PAQUES,
        annee_academique="2026-2027",
        date_debut="2026-04-05",
        date_fin="2026-04-10",
    )
    return CoursDeSession.objects.create(session=session, cours=cours, enseignant=professeur)


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
    @override_settings(DOCUMENTS_PDF_LOCAL_FALLBACK=True)
    @patch("apps.documents.tasks.generer_document_administratif.apply_async")
    @patch("apps.documents.tasks.Thread")
    def test_en_developpement_redis_n_est_pas_contacte(self, thread, publier, client, etudiant):
        client.force_login(etudiant.utilisateur)

        reponse = client.post(
            reverse(
                "documents:generate",
                kwargs={"document_type": DocumentAdministratif.TypeDocument.ATTESTATION},
            )
        )

        assert reponse.status_code == 302
        publier.assert_not_called()
        thread.assert_called_once()
        thread.return_value.start.assert_called_once_with()

    @override_settings(CELERY_TASK_ALWAYS_EAGER=False)
    @patch("apps.documents.tasks.generer_document_administratif.apply_async")
    def test_la_generation_est_planifiee_sans_bloquer_la_requete(self, publier, client, etudiant):
        client.force_login(etudiant.utilisateur)

        reponse = client.post(
            reverse(
                "documents:generate",
                kwargs={"document_type": DocumentAdministratif.TypeDocument.ATTESTATION},
            )
        )

        document = DocumentAdministratif.objects.get(etudiant=etudiant.utilisateur)
        assert reponse.status_code == 302
        assert document.statut_generation == document.StatutGeneration.EN_ATTENTE
        assert not document.fichier_pdf
        publier.assert_called_once_with(
            args=(document.pk, str(document.jeton_generation)),
            ignore_result=True,
            retry=False,
        )

    @override_settings(CELERY_TASK_ALWAYS_EAGER=False)
    @patch(
        "apps.documents.tasks.generer_document_administratif.apply_async",
        side_effect=ConnectionError("Redis indisponible"),
    )
    def test_un_broker_indisponible_met_immediatement_le_document_en_echec(self, publier, client, etudiant):
        client.force_login(etudiant.utilisateur)

        reponse = client.post(
            reverse(
                "documents:generate",
                kwargs={"document_type": DocumentAdministratif.TypeDocument.ATTESTATION},
            )
        )

        document = DocumentAdministratif.objects.get(etudiant=etudiant.utilisateur)
        assert reponse.status_code == 302
        assert document.statut_generation == document.StatutGeneration.ECHEC
        assert document.erreur_generation
        publier.assert_called_once_with(
            args=(document.pk, str(document.jeton_generation)),
            ignore_result=True,
            retry=False,
        )

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
        """
        Le contenu du relevé vient des crédits réellement acquis.

        L'assertion porte sur le texte imprimé, et non sur le code de réponse :
        un relevé vide, un gabarit qui aurait perdu la colonne des crédits ou
        un total détaché de ses lignes rendraient tous les trois un 302
        parfaitement rassurant.
        """
        pytest.importorskip("weasyprint", reason="Le moteur PDF n'est pas installé dans cet environnement.")
        fitz = pytest.importorskip("fitz", reason="PyMuPDF est nécessaire pour relire le PDF produit.")

        settings.MEDIA_ROOT = tmp_path
        cours_session = _cours_de_session(etudiant)
        # Le relevé n'est délivré qu'à partir d'une note publiée : sans elle,
        # la vue refuse et il n'y aurait aucun PDF à relire.
        Evaluation.objects.create(
            etudiant=etudiant,
            cours_session=cours_session,
            statut=Evaluation.StatutEvaluation.PUBLIE,
            note="15",
            ects_valides="2.5",
        )
        CreditECTS.objects.create(
            etudiant=etudiant,
            cours=cours_session.cours,
            session=cours_session.session,
            ects_obtenus=2.5,
            source=CreditECTS.SourceCredit.ITEAG,
            date_validation="2026-04-10",
        )

        client.force_login(etudiant.utilisateur)
        reponse = client.post(
            reverse("documents:generate", kwargs={"document_type": DocumentAdministratif.TypeDocument.RELEVE_NOTES})
        )
        assert reponse.status_code in (200, 302)

        document = DocumentAdministratif.objects.get(
            etudiant=etudiant.utilisateur,
            type_document=DocumentAdministratif.TypeDocument.RELEVE_NOTES,
        )
        document.fichier_pdf.seek(0)
        with fitz.open(stream=document.fichier_pdf.read(), filetype="pdf") as pdf:
            contenu = "\n".join(page.get_text() for page in pdf)

        assert "Exégèse de Romains" in contenu
        # Le site est en français : Django formate les décimaux avec une
        # virgule. C'est le rendu attendu sur un document officiel français.
        assert "2,5" in contenu
        assert etudiant.numero_etudiant in contenu


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

    def test_suppression_document_par_etudiant(self, client, etudiant):
        document = DocumentAdministratif.objects.create(
            etudiant=etudiant.utilisateur,
            type_document=DocumentAdministratif.TypeDocument.ATTESTATION,
        )
        client.force_login(etudiant.utilisateur)
        reponse = client.post(reverse("documents:delete", kwargs={"pk": document.pk}))
        assert reponse.status_code == 302
        assert not DocumentAdministratif.objects.filter(pk=document.pk).exists()

    def test_un_etudiant_ne_peut_pas_supprimer_le_document_d_un_autre(self, client, etudiant, autre_etudiant):
        document = DocumentAdministratif.objects.create(
            etudiant=autre_etudiant.utilisateur,
            type_document=DocumentAdministratif.TypeDocument.ATTESTATION,
        )
        client.force_login(etudiant.utilisateur)
        reponse = client.post(reverse("documents:delete", kwargs={"pk": document.pk}))
        assert reponse.status_code == 404
        assert DocumentAdministratif.objects.filter(pk=document.pk).exists()
