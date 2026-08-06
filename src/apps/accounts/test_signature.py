from io import BytesIO
from unittest.mock import patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from PIL import Image

from apps.accounts.models import User
from apps.documents.models import DocumentRedige
from apps.documents.services_generation import fabriquer_document_redige

pytestmark = pytest.mark.django_db


def image_png(nom="signature.png"):
    contenu = BytesIO()
    Image.new("RGBA", (120, 40), (255, 255, 255, 0)).save(contenu, format="PNG")
    return SimpleUploadedFile(nom, contenu.getvalue(), content_type="image/png")


@pytest.fixture
def secretaire(db):
    return User.objects.create_user(username="signature-sec", role=User.Role.SECRETARIAT)


@pytest.fixture
def directeur(db):
    return User.objects.create_user(username="signature-dir", role=User.Role.ADMIN)


def test_le_secretariat_peut_enregistrer_sa_signature(client, secretaire, tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    client.force_login(secretaire)

    reponse = client.post(reverse("accounts:signature"), {"signature": image_png()})

    secretaire.refresh_from_db()
    assert reponse.status_code == 302
    assert secretaire.signature.name.startswith("comptes/signatures/")


def test_la_direction_accede_a_son_onglet(client, directeur):
    client.force_login(directeur)

    reponse = client.get(reverse("accounts:signature"))

    assert reponse.status_code == 200
    assert "Ma signature" in reponse.content.decode()


def test_un_enseignant_ne_peut_pas_deposer_de_signature(client, db):
    enseignant = User.objects.create_user(username="signature-prof", role=User.Role.ENSEIGNANT)
    client.force_login(enseignant)

    assert client.get(reverse("accounts:signature")).status_code in (302, 403)


def test_le_pdf_utilise_la_signature_de_son_redacteur(secretaire, directeur, tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    secretaire.signature = image_png("secretaire.png")
    secretaire.save(update_fields=["signature"])
    directeur.signature = image_png("directeur.png")
    directeur.save(update_fields=["signature"])
    document = DocumentRedige.objects.create(
        titre="Courrier signé",
        objet="Objet",
        corps="<p>Contenu.</p>",
        redige_par=secretaire,
    )

    with patch("apps.documents.services_generation.rendre_pdf", return_value=b"pdf") as rendre:
        fabriquer_document_redige(document)

    contexte = rendre.call_args.args[1]
    assert contexte["signature_pdf"].startswith("data:image/png;base64,")
    assert contexte["signature_pdf"] != ""
