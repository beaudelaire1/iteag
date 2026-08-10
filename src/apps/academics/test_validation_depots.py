"""
Une même question, une même réponse — quelle que soit la porte d'entrée.

La candidature vérifiait le contenu réel des fichiers déposés ; la remise de
devoir ne regardait que l'extension et la taille. Un fichier HTML renommé en
`.pdf` était donc refusé d'un côté et accepté de l'autre. Le risque immédiat
était faible — le déposant est authentifié, les médias sont servis depuis
l'origine R2 — mais deux règles pour une même question finissent toujours par
diverger, et c'est ce que ces tests empêchent.
"""

from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.academics.forms import REGLE_COPIE, REGLE_JUSTIFICATIF_PAIEMENT, StudentSubmissionForm
from apps.core.validation_fichiers import valider_fichier

FAUX_PDF = b"<html><body>Ceci n'est pas un PDF.</body></html>"
VRAI_PDF = b"%PDF-1.7\n%contenu"


def _docx() -> bytes:
    tampon = BytesIO()
    with ZipFile(tampon, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types></Types>")
        archive.writestr("word/document.xml", "<w:document></w:document>")
    return tampon.getvalue()


class TestLaRemiseDeDevoirControleLeContenu:
    def test_un_html_renomme_en_pdf_est_refuse(self):
        """Le test que réclamait l'audit : ce refus n'existait qu'à la candidature."""
        copie = SimpleUploadedFile("devoir.pdf", FAUX_PDF, content_type="application/pdf")
        formulaire = StudentSubmissionForm(files={"fichier_soumis": copie})

        assert not formulaire.is_valid()
        assert "contenu du fichier" in formulaire.errors["fichier_soumis"][0]

    def test_une_copie_authentique_passe(self):
        copie = SimpleUploadedFile("devoir.pdf", VRAI_PDF, content_type="application/pdf")
        formulaire = StudentSubmissionForm(files={"fichier_soumis": copie})

        assert formulaire.is_valid(), formulaire.errors
        # Le curseur revient à zéro : le stockage qui suit doit recevoir tous
        # les octets, pas ceux qui restent après la lecture de l'en-tête.
        assert formulaire.cleaned_data["fichier_soumis"].tell() == 0

    def test_un_docx_authentique_passe(self):
        copie = SimpleUploadedFile(
            "devoir.docx",
            _docx(),
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        formulaire = StudentSubmissionForm(files={"fichier_soumis": copie})

        assert formulaire.is_valid(), formulaire.errors

    def test_une_archive_zip_quelconque_ne_passe_pas_pour_un_docx(self):
        tampon = BytesIO()
        with ZipFile(tampon, "w", ZIP_DEFLATED) as archive:
            archive.writestr("charge.txt", "pas un document Word")
        copie = SimpleUploadedFile(
            "devoir.docx",
            tampon.getvalue(),
            content_type="application/zip",
        )
        formulaire = StudentSubmissionForm(files={"fichier_soumis": copie})

        assert not formulaire.is_valid()

    def test_une_image_n_est_pas_une_copie(self):
        """La règle de la remise reste plus étroite que celle des justificatifs."""
        copie = SimpleUploadedFile("devoir.png", b"\x89PNG\r\n\x1a\nPNG", content_type="image/png")
        formulaire = StudentSubmissionForm(files={"fichier_soumis": copie})

        assert not formulaire.is_valid()
        assert "Formats acceptés" in formulaire.errors["fichier_soumis"][0]

    def test_le_champ_annonce_les_memes_formats_qu_il_accepte(self):
        """
        Un `accept` plus large que la règle serveur promet un dépôt qui sera
        refusé après l'attente du téléversement.
        """
        accept = StudentSubmissionForm().fields["fichier_soumis"].widget.attrs["accept"]
        assert set(accept.split(",")) == set(REGLE_COPIE.extensions)


class TestLeJustificatifDePaiementSuitLaMemeRegle:
    def test_un_html_renomme_en_pdf_est_refuse(self):
        faux = SimpleUploadedFile("recu.pdf", FAUX_PDF, content_type="application/pdf")

        with pytest.raises(ValidationError, match="contenu du fichier"):
            valider_fichier(faux, REGLE_JUSTIFICATIF_PAIEMENT)

    def test_un_recu_scanne_passe(self):
        recu = SimpleUploadedFile("recu.jpg", b"\xff\xd8\xff\xe0JPEG", content_type="image/jpeg")

        assert valider_fichier(recu, REGLE_JUSTIFICATIF_PAIEMENT) is recu

    def test_sa_limite_de_taille_lui_est_propre(self):
        """Cinq mégaoctets pour un reçu, dix pour une copie : les deux tiennent."""
        trop_gros = SimpleUploadedFile(
            "recu.pdf",
            VRAI_PDF + b"x" * REGLE_JUSTIFICATIF_PAIEMENT.taille_max,
            content_type="application/pdf",
        )

        with pytest.raises(ValidationError, match="dépasse 5 Mo"):
            valider_fichier(trop_gros, REGLE_JUSTIFICATIF_PAIEMENT)


def test_les_trois_regles_partagent_le_meme_controle():
    """
    L'extraction n'a de valeur que si personne ne réécrit le contrôle à côté.
    Si un formulaire recommence à comparer des extensions à la main, ce test ne
    le verra pas — mais la revue, elle, saura où regarder.
    """
    from apps.admissions.formulaires import REGLE_PIECES

    for regle in (REGLE_COPIE, REGLE_JUSTIFICATIF_PAIEMENT, REGLE_PIECES):
        faux = SimpleUploadedFile("piece.pdf", FAUX_PDF, content_type="application/pdf")
        with pytest.raises(ValidationError, match="contenu du fichier"):
            valider_fichier(faux, regle)
