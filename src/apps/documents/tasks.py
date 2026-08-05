"""Tâches Celery de génération PDF pour l'app Documents."""

import logging
from threading import Thread
from time import perf_counter

from django.conf import settings
from django.core.files.base import ContentFile
from django.db import close_old_connections

from apps.core.services.pdf import precharger_moteur_pdf
from celery import shared_task, signals

from .models import DocumentAdministratif, DocumentRedige, SuiviGenerationPDF
from .services_generation import fabriquer_document_administratif, fabriquer_document_redige

logger = logging.getLogger(__name__)


@signals.worker_process_init.connect
def _precharger_pdf_du_worker(**kwargs):
    """Paie l'initialisation WeasyPrint avant l'arrivée du premier document."""
    debut = perf_counter()
    try:
        precharger_moteur_pdf(profil_polices="document_administratif")
    except Exception:  # noqa: BLE001 - le worker doit rester disponible pour les autres tâches
        logger.warning("Préchargement de WeasyPrint impossible", exc_info=True)
        return
    logger.info("Moteur PDF préchargé en %.3f s", perf_counter() - debut)


def _echouer(modele, pk, jeton, *, journal=False):
    message = "La génération PDF a échoué. Réessayez ou contactez le secrétariat."
    modele.objects.filter(pk=pk, jeton_generation=jeton).update(
        statut_generation=SuiviGenerationPDF.StatutGeneration.ECHEC,
        erreur_generation=message,
    )
    if journal:
        logger.exception("Échec de génération PDF pour %s:%s", modele.__name__, pk)


def _executer(modele, pk, jeton, fabriquer):
    debut = perf_counter()
    document = modele.objects.filter(pk=pk, jeton_generation=jeton).first()
    if document is None:
        return "obsolete"
    if document.fichier_pdf and document.statut_generation == document.StatutGeneration.PRET:
        return "deja_genere"

    modele.objects.filter(pk=pk, jeton_generation=jeton).update(
        statut_generation=document.StatutGeneration.EN_COURS,
        erreur_generation="",
    )
    try:
        contenu, nom = fabriquer(document)
    except Exception:  # noqa: BLE001 - le détail reste dans les journaux Celery
        _echouer(modele, pk, jeton, journal=True)
        return "echec"

    document = modele.objects.filter(pk=pk, jeton_generation=jeton).first()
    if document is None:
        return "obsolete"
    document.fichier_pdf.save(nom, ContentFile(contenu), save=False)
    document.statut_generation = document.StatutGeneration.PRET
    document.erreur_generation = ""
    document.save(update_fields=["fichier_pdf", "statut_generation", "erreur_generation", "updated_at"])
    logger.info(
        "PDF généré pour %s:%s en %.3f s",
        modele.__name__,
        pk,
        perf_counter() - debut,
    )
    return "genere"


def _executer_localement(modele, pk, jeton, fabriquer):
    """Exécute un rendu hors requête avec sa propre connexion Django."""
    close_old_connections()
    try:
        _executer(modele, pk, jeton, fabriquer)
    finally:
        close_old_connections()


def _planifier_localement(modele, document, jeton, fabriquer) -> None:
    Thread(
        target=_executer_localement,
        args=(modele, document.pk, jeton, fabriquer),
        name=f"pdf-{modele.__name__}-{document.pk}",
        daemon=True,
    ).start()


@shared_task(name="documents.generer_document_administratif", ignore_result=True)
def generer_document_administratif(document_id: int, jeton: str) -> str:
    return _executer(
        DocumentAdministratif,
        document_id,
        jeton,
        fabriquer_document_administratif,
    )


@shared_task(name="documents.generer_document_redige", ignore_result=True)
def generer_document_redige(document_id: int, jeton: str) -> str:
    return _executer(DocumentRedige, document_id, jeton, fabriquer_document_redige)


def planifier_document_administratif(document: DocumentAdministratif) -> bool:
    jeton = document.preparer_generation()
    if settings.DOCUMENTS_PDF_LOCAL_FALLBACK:
        _planifier_localement(
            DocumentAdministratif,
            document,
            jeton,
            fabriquer_document_administratif,
        )
        return True
    try:
        generer_document_administratif.apply_async(
            args=(document.pk, str(jeton)),
            ignore_result=True,
            retry=False,
        )
    except Exception as exc:  # noqa: BLE001 - Redis indisponible, état visible dans l'interface
        _echouer(DocumentAdministratif, document.pk, jeton)
        logger.warning("Publication Celery impossible pour DocumentAdministratif:%s : %s", document.pk, exc)
        return False
    return True


def planifier_document_redige(document: DocumentRedige) -> bool:
    jeton = document.preparer_generation()
    if settings.DOCUMENTS_PDF_LOCAL_FALLBACK:
        _planifier_localement(DocumentRedige, document, jeton, fabriquer_document_redige)
        return True
    try:
        generer_document_redige.apply_async(
            args=(document.pk, str(jeton)),
            ignore_result=True,
            retry=False,
        )
    except Exception as exc:  # noqa: BLE001
        _echouer(DocumentRedige, document.pk, jeton)
        logger.warning("Publication Celery impossible pour DocumentRedige:%s : %s", document.pk, exc)
        return False
    return True
