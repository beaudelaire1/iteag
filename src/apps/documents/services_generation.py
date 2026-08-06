"""Composition des PDF de l'app Documents, sans dépendance à une requête."""

import base64
import mimetypes

from django.utils import timezone
from django.utils.text import slugify

from apps.academics.models import Paiement
from apps.core.services.pdf import contexte_marque, rendre_pdf

from .models import DocumentAdministratif, DocumentRedige


def _user_signature_uri(user) -> str:
    if user is None or not user.signature:
        return ""
    try:
        type_mime = mimetypes.guess_type(user.signature.name)[0] or "image/png"
        with user.signature.open("rb") as fichier:
            contenu = base64.b64encode(fichier.read()).decode("ascii")
        return f"data:{type_mime};base64,{contenu}"
    except Exception:
        return ""


def _signature_uri(document: DocumentRedige) -> str:
    redacteur = document.redige_par
    return _user_signature_uri(redacteur)


def obtenir_signature_secretariat_data_uri() -> tuple[str, str]:
    """Retourne (signature_data_uri, nom_du_signataire) du secrétariat ou de la direction.

    Cherche d'abord un utilisateur du secrétariat ayant déposé une signature numérique,
    puis à défaut un administrateur ayant une signature, puis tout utilisateur avec signature.
    """
    from django.contrib.auth import get_user_model

    User = get_user_model()
    secretaire = (
        User.objects.filter(role="secretariat", signature__isnull=False)
        .exclude(signature="")
        .order_by("-id")
        .first()
    )
    if not secretaire:
        secretaire = (
            User.objects.filter(role="admin", signature__isnull=False)
            .exclude(signature="")
            .order_by("-id")
            .first()
        )
    if not secretaire:
        secretaire = (
            User.objects.filter(signature__isnull=False)
            .exclude(signature="")
            .order_by("-id")
            .first()
        )

    if not secretaire:
        return "", ""

    uri = _user_signature_uri(secretaire)
    nom = secretaire.get_full_name() or secretaire.username
    return uri, nom


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

    signature_pdf, secretariat_nom = obtenir_signature_secretariat_data_uri()

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
            signature_pdf=signature_pdf,
            secretariat_nom=secretariat_nom,
        ),
    )
    identite = slugify(utilisateur.get_full_name() or utilisateur.username)
    nom = f"{document.type_document}-{identite}-{genere_le:%Y%m%d%H%M%S}.pdf"
    return contenu, nom


def fabriquer_document_redige(document: DocumentRedige) -> tuple[bytes, str]:
    genere_le = timezone.now()
    signature_pdf = _signature_uri(document)
    signataire_nom = document.signataire_nom

    if not signature_pdf:
        sec_signature_pdf, sec_nom = obtenir_signature_secretariat_data_uri()
        signature_pdf = sec_signature_pdf
        if not signataire_nom:
            signataire_nom = sec_nom

    contenu = rendre_pdf(
        "documents/pdf/document_redige.html",
        contexte_marque(
            profil_polices="document_administratif",
            document=document,
            edite_le=genere_le,
            signature_pdf=signature_pdf,
            signataire_nom_effectif=signataire_nom,
        ),
    )
    prefixe = "apercu" if document.est_modifiable else slugify(document.reference or document.titre)
    nom = f"{prefixe}-{slugify(document.titre) or 'document'}-{genere_le:%Y%m%d%H%M%S}.pdf"
    return contenu, nom
