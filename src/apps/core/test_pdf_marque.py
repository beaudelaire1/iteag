"""
Socle graphique des documents imprimés.

Le défaut corrigé ici ne produisait aucune erreur : les gabarits nommaient des
polices installées dans la seule image de production, et WeasyPrint retombait
ailleurs sur un substitut arbitraire. Le document remis à un étudiant depuis un
poste de travail ne ressemblait donc pas à celui qui avait été validé.

Ces cas vérifient le produit fini — le PDF —, pas le gabarit qui l'a écrit :
c'est la seule façon de constater qu'une police a bien été employée.
"""

import pytest

from apps.core.services import pdf as marque

pytestmark = pytest.mark.django_db

fitz = pytest.importorskip("fitz", reason="PyMuPDF est nécessaire pour relire le PDF produit")


def _polices_du_pdf(octets: bytes) -> set[str]:
    document = fitz.open(stream=octets, filetype="pdf")
    return {police[3] for page in document for police in page.get_fonts()}


def test_les_polices_du_depot_sont_trouvees():
    """Sept fichiers sont livrés : quatre graisses d'Inter, trois de Playfair."""
    polices = marque.polices_embarquees()
    assert len(polices) == 7
    assert {p["famille"] for p in polices} == {"Inter", "Playfair Display"}
    for police in polices:
        assert police["uri"].startswith("file:///")


def test_le_logo_est_encre_pour_le_papier():
    """Livré blanc sur fond transparent, il disparaissait sur le crème du document."""
    uri = marque.logo_uri()
    assert uri.startswith("data:image/png;base64,")

    import base64
    import io

    from PIL import Image

    image = Image.open(io.BytesIO(base64.b64decode(uri.split(",", 1)[1]))).convert("RGBA")
    visibles = [pixel for pixel in image.getdata() if pixel[3] > 40]
    assert visibles, "le logo encré ne contient aucun pixel opaque"
    assert all(pixel[:3] == marque.ENCRE_LOGO for pixel in visibles)


def test_l_attestation_emploie_les_polices_de_la_charte(module_certifiant_termine):
    """Aucune substitution : ni Times, ni Helvetica, ni police générique."""
    from django.template.loader import render_to_string
    from weasyprint import HTML

    attestation = module_certifiant_termine
    html = render_to_string(
        "elearning/attestation_pdf.html",
        marque.contexte_marque(
            attestation=attestation,
            qr_verification=marque.qr_data_uri("https://iteag.org/verification"),
        ),
    )
    octets = HTML(string=html).write_pdf()
    polices = _polices_du_pdf(octets)

    assert any("Playfair" in nom for nom in polices), polices
    assert any("Inter" in nom for nom in polices), polices
    assert not any("Times" in nom or "Helvetica" in nom for nom in polices), polices


def test_l_attestation_porte_le_logo_et_le_qr(module_certifiant_termine):
    from django.template.loader import render_to_string
    from weasyprint import HTML

    html = render_to_string(
        "elearning/attestation_pdf.html",
        marque.contexte_marque(
            attestation=module_certifiant_termine,
            qr_verification=marque.qr_data_uri("https://iteag.org/verification"),
        ),
    )
    document = fitz.open(stream=HTML(string=html).write_pdf(), filetype="pdf")
    assert len(document[0].get_images()) == 2, "le logo et le QR doivent être présents"


def test_l_attestation_imprime_les_accents(module_certifiant_termine):
    """Le nom de l'institut est le premier endroit où une substitution se voit."""
    from django.template.loader import render_to_string
    from weasyprint import HTML

    html = render_to_string(
        "elearning/attestation_pdf.html",
        marque.contexte_marque(attestation=module_certifiant_termine, qr_verification=""),
    )
    document = fitz.open(stream=HTML(string=html).write_pdf(), filetype="pdf")
    texte = document[0].get_text()
    assert "Théologie Évangélique" in texte
    assert "Il est attesté que" in texte


@pytest.fixture
def module_certifiant_termine(db):
    from datetime import date

    from apps.academics.models import ProfilEtudiant, Promotion
    from apps.accounts.models import User
    from apps.elearning.models import AttestationModule, InscriptionModule, ModuleFormation
    from apps.formations.models import Parcours

    parcours = Parcours.objects.create(
        nom="Parcours d'essai", slug="parcours-essai", type_parcours=Parcours.TypeParcours.LIBRE
    )
    promotion = Promotion.objects.create(nom="Promotion d'essai", parcours=parcours, annee_debut=2026, annee_fin=2029)
    utilisateur = User.objects.create_user(
        username="apprenant",
        email="apprenant@iteag.org",
        password="MotDePasse!2026",
        first_name="Léonie",
        last_name="Abaul",
    )
    profil = ProfilEtudiant.objects.create(
        utilisateur=utilisateur, parcours=parcours, promotion=promotion, numero_etudiant="ETU-PDF-001"
    )
    module = ModuleFormation.objects.create(
        titre="L'éthique chrétienne", slug="ethique-chretienne", certifiant=True, ects=2.5
    )
    inscription = InscriptionModule.objects.create(
        etudiant=profil, module=module, statut=InscriptionModule.StatutAcces.TERMINE, date_debut_acces=date(2026, 1, 1)
    )
    return AttestationModule.objects.create(inscription=inscription)
