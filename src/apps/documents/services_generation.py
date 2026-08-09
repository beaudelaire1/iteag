"""Composition des PDF de l'app Documents, sans dépendance à une requête."""

import base64
import logging
import mimetypes

from django.utils import timezone
from django.utils.text import slugify

from apps.academics.models import Paiement
from apps.core.services.pdf import contexte_marque, rendre_pdf

from .models import DocumentAdministratif, DocumentRedige

logger = logging.getLogger(__name__)


class SignatureIllisible(Exception):
    """Une signature est déposée, mais son fichier n'a pas pu être lu.

    Distinct du cas « aucune signature déposée », qui est une dégradation
    acceptable et volontaire. Ici le stockage a répondu autre chose que le
    fichier attendu — panne R2, objet supprimé, droits retirés — et produire
    quand même le document reviendrait à délivrer une pièce qui porte la date,
    le nom et la qualité d'un signataire, mais pas sa signature.
    """


def _user_signature_uri(user) -> str:
    """Signature d'un utilisateur en « data: URI », ou chaîne vide s'il n'en a pas.

    Lève ``SignatureIllisible`` si une signature est déposée mais illisible :
    l'appelant décide alors s'il peut dégrader ou s'il doit refuser. Avaler
    l'erreur ici la rendrait indiscernable d'une absence de signature, et le
    défaut ne se verrait que sur le PDF remis à l'étudiant.
    """
    if user is None or not user.signature:
        return ""
    try:
        type_mime = mimetypes.guess_type(user.signature.name)[0] or "image/png"
        with user.signature.open("rb") as fichier:
            contenu = base64.b64encode(fichier.read()).decode("ascii")
    except Exception as erreur:
        logger.exception(
            "Signature illisible pour l'utilisateur %s (fichier « %s »)",
            getattr(user, "pk", "?"),
            getattr(user.signature, "name", "?"),
        )
        raise SignatureIllisible(str(erreur)) from erreur
    return f"data:{type_mime};base64,{contenu}"


def _signature_uri(document: DocumentRedige) -> str:
    redacteur = document.redige_par
    return _user_signature_uri(redacteur)


def obtenir_signature_secretariat_data_uri() -> tuple[str, str, str]:
    """Retourne (signature_data_uri, nom_du_signataire, qualite_du_signataire) du secrétariat ou de la direction.

    Cherche d'abord un utilisateur du secrétariat ayant déposé une signature numérique,
    puis à défaut un administrateur ayant une signature, puis tout utilisateur avec signature.
    """
    from django.contrib.auth import get_user_model

    User = get_user_model()
    secretaire = (
        User.objects.filter(role="secretariat", signature__isnull=False).exclude(signature="").order_by("-id").first()
    )
    if not secretaire:
        secretaire = (
            User.objects.filter(role="admin", signature__isnull=False).exclude(signature="").order_by("-id").first()
        )
    if not secretaire:
        secretaire = User.objects.filter(signature__isnull=False).exclude(signature="").order_by("-id").first()

    if not secretaire:
        return "", "", ""

    uri = _user_signature_uri(secretaire)
    nom = secretaire.nom_autorite_signature or secretaire.get_full_name() or secretaire.username
    qualite = secretaire.titre_qualite_signature or "Le secrétariat"
    return uri, nom, qualite


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

    signature_pdf, secretariat_nom, secretariat_qualite = obtenir_signature_secretariat_data_uri()

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
            secretariat_qualite=secretariat_qualite,
        ),
    )
    nom_fichier = f"{document.reference_document.lower().replace('/', '_')}.pdf"
    return contenu, nom_fichier


def fabriquer_document_redige(document: DocumentRedige) -> tuple[bytes, str]:
    genere_le = timezone.now()
    redacteur = document.redige_par
    signature_pdf = _user_signature_uri(redacteur) if redacteur else ""
    signataire_nom_effectif = (
        document.signataire_nom
        or (redacteur.nom_autorite_signature if redacteur else "")
        or (redacteur.get_full_name() if redacteur else "")
        or (redacteur.username if redacteur else "")
    )
    signataire_qualite_effectif = document.signataire_qualite or (
        redacteur.titre_qualite_signature if redacteur and redacteur.titre_qualite_signature else ""
    )

    if not signature_pdf:
        signature_pdf, sec_nom, sec_qualite = obtenir_signature_secretariat_data_uri()
        if not signataire_nom_effectif:
            signataire_nom_effectif = sec_nom
        if not signataire_qualite_effectif:
            signataire_qualite_effectif = sec_qualite

    contenu = rendre_pdf(
        "documents/pdf/document_redige.html",
        contexte_marque(
            profil_polices="document_redige",
            document=document,
            edite_le=genere_le,
            signature_pdf=signature_pdf,
            signataire_nom_effectif=signataire_nom_effectif,
            signataire_qualite_effectif=signataire_qualite_effectif,
        ),
    )
    prefixe = "apercu" if document.est_modifiable else slugify(document.reference or document.titre)
    nom = f"{prefixe}-{slugify(document.titre) or 'document'}-{genere_le:%Y%m%d%H%M%S}.pdf"
    return contenu, nom
