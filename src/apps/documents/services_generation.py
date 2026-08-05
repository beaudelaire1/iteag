"""Composition des PDF de l'app Documents, sans dépendance à une requête."""

from django.utils import timezone
from django.utils.text import slugify

from apps.academics.models import Paiement
from apps.core.services.pdf import contexte_marque, rendre_pdf

from .models import DocumentAdministratif, DocumentRedige


def fabriquer_document_administratif(document: DocumentAdministratif) -> tuple[bytes, str]:
    utilisateur = document.etudiant
    profil = utilisateur.profil_etudiant
    evaluations = profil.evaluations.filter(statut="publie").select_related(
        "cours_session__cours",
        "cours_session__session",
    )
    paiements = profil.paiements.filter(statut=Paiement.StatutPaiement.CONFIRME).select_related("session")
    credits = profil.credits_ects.select_related("cours", "session", "stage", "vae").order_by("date_validation")
    if document.type_document == DocumentAdministratif.TypeDocument.RELEVE_NOTES:
        profil.ects_acquis_annotes = profil.total_ects_acquis

    genere_le = timezone.now()
    contenu = rendre_pdf(
        "documents/pdf/document.html",
        contexte_marque(
            profil_polices="document_administratif",
            document=document,
            user=utilisateur,
            profil=profil,
            document_type=document.type_document,
            document_label=document.get_type_document_display(),
            generated_at=genere_le,
            evaluations=evaluations,
            paiements=paiements,
            credits=credits,
        ),
    )
    identite = slugify(utilisateur.get_full_name() or utilisateur.username)
    nom = f"{document.type_document}-{identite}-{genere_le:%Y%m%d%H%M%S}.pdf"
    return contenu, nom


def fabriquer_document_redige(document: DocumentRedige) -> tuple[bytes, str]:
    genere_le = timezone.now()
    contenu = rendre_pdf(
        "documents/pdf/document_redige.html",
        contexte_marque(
            profil_polices="document_administratif",
            document=document,
            edite_le=genere_le,
        ),
    )
    prefixe = "apercu" if document.est_modifiable else slugify(document.reference or document.titre)
    nom = f"{prefixe}-{slugify(document.titre) or 'document'}-{genere_le:%Y%m%d%H%M%S}.pdf"
    return contenu, nom
