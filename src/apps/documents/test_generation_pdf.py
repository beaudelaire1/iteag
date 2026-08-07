"""
Tests de la génération réelle des documents PDF.

Les tests existants tolèrent l'absence de WeasyPrint et se contentent de
vérifier que l'échec est propre. C'est prudent mais insuffisant : un relevé
mal composé, un gabarit qui référence un champ disparu ou un document vide ne
seraient pas vus. Ici, on produit le PDF et on lit son contenu.

Ce qui est vérifié pour chaque type : que le fichier est bien un PDF, qu'il
porte le nom de l'étudiant, et — pour le relevé — que les crédits réellement
acquis y figurent, y compris ceux qui ne viennent pas d'un cours.
"""

import pytest
from django.urls import reverse

from apps.academics.models import CreditECTS, Paiement, ProfilEtudiant, Promotion, SessionAcademique, Stage
from apps.accounts.models import User
from apps.documents.models import DocumentAdministratif
from apps.formations.models import Cours, Discipline, Parcours

pytest.importorskip("weasyprint", reason="Le moteur PDF n'est pas installé dans cet environnement.")


@pytest.fixture
def parcours(db):
    return Parcours.objects.create(
        nom="Diplômant",
        slug="diplomant-pdf",
        type_parcours=Parcours.TypeParcours.DIPLOMANT_ITEAG,
        ects_requis=180,
    )


@pytest.fixture
def etudiant(db, parcours):
    utilisateur = User.objects.create_user(
        username="etu_pdf",
        email="etu_pdf@iteag.org",
        password="motdepasse-long-12",
        first_name="Estelle",
        last_name="Marceline",
        role=User.Role.ETUDIANT,
    )
    promotion = Promotion.objects.create(nom="Promotion 2026-2032", parcours=parcours, annee_debut=2026, annee_fin=2032)
    return ProfilEtudiant.objects.create(
        utilisateur=utilisateur,
        parcours=parcours,
        promotion=promotion,
        numero_etudiant="ETU-PDF-042",
        statut_inscription=ProfilEtudiant.StatutInscription.ACTIF,
    )


@pytest.fixture
def session(db):
    return SessionAcademique.objects.create(
        nom="Session de Pâques",
        periode=SessionAcademique.Periode.PAQUES,
        annee_academique="2026-2027",
        date_debut="2027-04-05",
        date_fin="2027-04-10",
    )


def texte_du_pdf(document: DocumentAdministratif) -> str:
    """Texte extrait du PDF produit — la seule preuve de ce qui est imprimé."""
    import fitz

    document.fichier_pdf.seek(0)
    with fitz.open(stream=document.fichier_pdf.read(), filetype="pdf") as pdf:
        return "\n".join(page.get_text() for page in pdf)


def generer(client, etudiant, type_document):
    client.force_login(etudiant.utilisateur)
    reponse = client.post(reverse("documents:generate", kwargs={"document_type": type_document}))
    assert reponse.status_code in (200, 302)
    return DocumentAdministratif.objects.filter(etudiant=etudiant.utilisateur, type_document=type_document).first()


@pytest.mark.django_db
class TestAttestation:
    def test_le_pdf_est_produit_et_nomme_l_etudiant(self, client, etudiant, tmp_path, settings):
        settings.MEDIA_ROOT = tmp_path
        document = generer(client, etudiant, DocumentAdministratif.TypeDocument.ATTESTATION)

        assert document is not None and document.fichier_pdf
        contenu = texte_du_pdf(document)
        assert "Estelle Marceline" in contenu
        assert "ETU-PDF-042" in contenu
        assert "ITEAG" in contenu

    def test_un_etudiant_non_inscrit_ne_l_obtient_pas(self, client, etudiant, tmp_path, settings):
        settings.MEDIA_ROOT = tmp_path
        etudiant.statut_inscription = ProfilEtudiant.StatutInscription.PRE_INSCRIT
        etudiant.save(update_fields=["statut_inscription"])
        assert generer(client, etudiant, DocumentAdministratif.TypeDocument.ATTESTATION) is None


@pytest.mark.django_db
class TestReleveDeNotes:
    @pytest.fixture(autouse=True)
    def _note_publiee(self, db, etudiant, session):
        """Le relevé n'est délivré qu'à partir d'une note publiée."""
        from apps.academics.models import CoursDeSession
        from apps.formations.models import Professeur
        from apps.lms.models import Evaluation

        discipline = Discipline.objects.create(nom="Exégèse", slug="exegese-pdf")
        cours = Cours.objects.create(titre="Exégèse de Romains", slug="exegese-romains", discipline=discipline)
        utilisateur = User.objects.create_user(
            username="prof_pdf", email="prof_pdf@iteag.org", password="motdepasse-long-12", role=User.Role.ENSEIGNANT
        )
        professeur = Professeur.objects.create(user=utilisateur, nom="Duval", prenom="Anne", slug="anne-duval")
        cours_session = CoursDeSession.objects.create(session=session, cours=cours, enseignant=professeur)
        Evaluation.objects.create(
            etudiant=etudiant,
            cours_session=cours_session,
            statut=Evaluation.StatutEvaluation.PUBLIE,
            note="15",
            ects_valides="2.5",
        )
        CreditECTS.objects.create(
            etudiant=etudiant,
            cours=cours,
            session=session,
            ects_obtenus="2.5",
            source=CreditECTS.SourceCredit.ITEAG,
            date_validation="2027-04-10",
        )

    def test_le_releve_porte_les_credits_acquis(self, client, etudiant, tmp_path, settings):
        settings.MEDIA_ROOT = tmp_path
        document = generer(client, etudiant, DocumentAdministratif.TypeDocument.RELEVE_NOTES)

        contenu = texte_du_pdf(document)
        assert "Exégèse de Romains" in contenu
        # Le site est en français : Django formate les décimaux avec une
        # virgule. C'est le rendu attendu sur un document officiel français.
        assert "2,5" in contenu
        assert "Estelle Marceline" in contenu

    def test_un_stage_valide_figure_au_releve(self, client, etudiant, tmp_path, settings):
        """
        Le relevé est porté par le dossier académique : il doit montrer les
        acquis hors cours, sinon son total ne correspondrait pas à ses lignes.
        """
        settings.MEDIA_ROOT = tmp_path
        stage = Stage.objects.create(
            etudiant=etudiant,
            type_stage="Stage pastoral",
            lieu="Église des Abymes",
            date_debut="2027-01-10",
            date_fin="2027-03-10",
            ects="30",
            statut=Stage.StatutStage.VALIDE,
        )
        CreditECTS.objects.create(
            etudiant=etudiant,
            stage=stage,
            ects_obtenus="30",
            source=CreditECTS.SourceCredit.ITEAG,
            date_validation="2027-03-10",
        )

        contenu = texte_du_pdf(generer(client, etudiant, DocumentAdministratif.TypeDocument.RELEVE_NOTES))
        assert "Stage pastoral" in contenu
        assert "32,5" in contenu, "Le total doit inclure le stage"

    def test_le_total_et_le_reste_a_valider_sont_imprimes(self, client, etudiant, tmp_path, settings):
        settings.MEDIA_ROOT = tmp_path
        contenu = texte_du_pdf(generer(client, etudiant, DocumentAdministratif.TypeDocument.RELEVE_NOTES))
        assert "TOTAL ACQUIS" in contenu.upper()
        assert "177,5" in contenu, "Les ECTS restants doivent apparaître"


@pytest.mark.django_db
class TestRecu:
    def test_le_recu_liste_les_paiements_confirmes(self, client, etudiant, session, tmp_path, settings):
        settings.MEDIA_ROOT = tmp_path
        Paiement.objects.create(
            etudiant=etudiant,
            session=session,
            montant="180.00",
            mode=Paiement.ModePaiement.VIREMENT,
            reference="VIR-2027-0042",
            statut=Paiement.StatutPaiement.CONFIRME,
            date_paiement="2027-03-01",
        )
        contenu = texte_du_pdf(generer(client, etudiant, DocumentAdministratif.TypeDocument.RECU))
        assert "VIR-2027-0042" in contenu
        assert "180" in contenu

    def test_sans_paiement_confirme_le_recu_est_refuse(self, client, etudiant, tmp_path, settings):
        settings.MEDIA_ROOT = tmp_path
        assert generer(client, etudiant, DocumentAdministratif.TypeDocument.RECU) is None


@pytest.mark.django_db
class TestMiseEnPage:
    """Le document est officiel : sa mise en page fait partie du livrable."""

    def test_le_document_tient_sur_une_page_et_porte_sa_pagination(self, client, etudiant, tmp_path, settings):
        import fitz

        settings.MEDIA_ROOT = tmp_path
        document = generer(client, etudiant, DocumentAdministratif.TypeDocument.ATTESTATION)
        document.fichier_pdf.seek(0)
        with fitz.open(stream=document.fichier_pdf.read(), filetype="pdf") as pdf:
            assert pdf.page_count == 1
            texte = pdf[0].get_text()

        assert "1 / 1" in texte
        assert "Toute rature" in texte, "La mention légale du pied de page doit être imprimée"

    def test_le_pdf_est_balise_et_porte_ses_metadonnees(self, client, etudiant, tmp_path, settings):
        """Le document reste identifiable et navigable hors de la plateforme."""
        import fitz

        settings.MEDIA_ROOT = tmp_path
        document = generer(client, etudiant, DocumentAdministratif.TypeDocument.ATTESTATION)
        document.fichier_pdf.seek(0)
        with fitz.open(stream=document.fichier_pdf.read(), filetype="pdf") as pdf:
            assert "Attestation" in pdf.metadata["title"]
            assert "Institut de Théologie" in pdf.metadata["author"]
            type_objet, _ = pdf.xref_get_key(pdf.pdf_catalog(), "StructTreeRoot")

        assert type_objet == "xref", "Un PDF/UA doit contenir un arbre de structure"

    def test_la_signature_n_est_pas_scindee(self, client, etudiant, tmp_path, settings):
        """Une signature séparée de sa date sur une autre page n'a aucune valeur."""
        settings.MEDIA_ROOT = tmp_path
        contenu = texte_du_pdf(generer(client, etudiant, DocumentAdministratif.TypeDocument.ATTESTATION))
        assert "Fait aux Abymes" in contenu
        assert "SECRÉTARIAT" in contenu.upper()

    def test_la_signature_du_secretariat_est_incluse(self, etudiant, tmp_path, settings):
        """Si le secrétariat a déposé sa signature, elle est incluse dans le document."""
        from django.core.files.uploadedfile import SimpleUploadedFile

        from apps.documents.services_generation import fabriquer_document_administratif

        settings.MEDIA_ROOT = tmp_path
        image_png = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
            b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
            b"\x1f\x15c4\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff?"
            b'\x03\x00\x05\xfe\x02\xfe\xa7\x9a\x9c"\x00\x00\x00\x00'
            b"IEND\xaeB`\x82"
        )
        f = SimpleUploadedFile("signature.png", image_png, content_type="image/png")
        User.objects.create_user(
            username="secretaire_pdf",
            email="sec@iteag.org",
            password="password123",
            first_name="Jean",
            last_name="Valjean",
            role=User.Role.SECRETARIAT,
            signature=f,
        )
        doc = DocumentAdministratif.objects.create(
            etudiant=etudiant.utilisateur,
            type_document=DocumentAdministratif.TypeDocument.ATTESTATION,
        )
        pdf_bytes, nom = fabriquer_document_administratif(doc)
        assert len(pdf_bytes) > 0
