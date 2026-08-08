"""Validation des justificatifs déposés par les candidats."""

from io import BytesIO
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.forms import ValidationError

from apps.admissions.forms import CandidatureForm
from apps.admissions.formulaires import TAILLE_MAX_PIECE, valider_fichier_piece


def _docx() -> bytes:
    tampon = BytesIO()
    with ZipFile(tampon, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types></Types>")
        archive.writestr("word/document.xml", "<w:document></w:document>")
    return tampon.getvalue()


def _odt() -> bytes:
    tampon = BytesIO()
    with ZipFile(tampon, "w") as archive:
        # La spécification ODF place normalement mimetype en premier et sans
        # compression ; le validateur n'exige que sa valeur, pas cet ordre.
        archive.writestr(
            "mimetype",
            "application/vnd.oasis.opendocument.text",
            compress_type=ZIP_STORED,
        )
        archive.writestr("content.xml", "<office:document-content></office:document-content>")
    return tampon.getvalue()


@pytest.mark.parametrize(
    ("nom", "contenu", "mime"),
    [
        ("identite.pdf", b"%PDF-1.7\n%test", "application/pdf"),
        ("photo.jpg", b"\xff\xd8\xff\xe0JPEG", "image/jpeg"),
        ("photo.png", b"\x89PNG\r\n\x1a\nPNG", "image/png"),
        ("ancien.doc", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1DOC", "application/msword"),
        (
            "diplome.docx",
            _docx(),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ),
        ("lettre.odt", _odt(), "application/vnd.oasis.opendocument.text"),
    ],
)
def test_formats_autorises_sont_acceptes(nom, contenu, mime):
    fichier = SimpleUploadedFile(nom, contenu, content_type=mime)

    assert valider_fichier_piece(fichier) is fichier
    assert fichier.tell() == 0


def test_extension_autorisee_avec_signature_incoherente_est_refusee():
    fichier = SimpleUploadedFile("identite.pdf", b"MZ-faux-pdf", content_type="application/pdf")

    with pytest.raises(ValidationError, match="contenu du fichier"):
        valider_fichier_piece(fichier)


def test_mime_incoherent_est_refuse_meme_si_signature_valide():
    fichier = SimpleUploadedFile("photo.png", b"\x89PNG\r\n\x1a\nPNG", content_type="text/html")

    with pytest.raises(ValidationError, match="type du fichier"):
        valider_fichier_piece(fichier)


def test_archive_zip_generique_ne_passe_pas_pour_un_docx():
    tampon = BytesIO()
    with ZipFile(tampon, "w", ZIP_DEFLATED) as archive:
        archive.writestr("payload.txt", "pas un document Word")
    fichier = SimpleUploadedFile(
        "diplome.docx",
        tampon.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )

    with pytest.raises(ValidationError, match="contenu du fichier"):
        valider_fichier_piece(fichier)


def test_fichier_trop_volumineux_est_refuse_avant_traitement():
    fichier = SimpleUploadedFile(
        "identite.pdf",
        b"%PDF-" + b"x" * TAILLE_MAX_PIECE,
        content_type="application/pdf",
    )

    with pytest.raises(ValidationError, match="dépasse 10 Mo"):
        valider_fichier_piece(fichier)


def test_candidature_initiale_applique_le_validateur_aux_trois_pieces():
    formulaire = CandidatureForm()

    for nom in ("piece_identite", "diplomes", "autre_document"):
        assert valider_fichier_piece in formulaire.fields[nom].validators
        assert formulaire.fields[nom].widget.attrs["accept"]
