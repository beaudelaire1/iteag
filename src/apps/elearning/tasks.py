"""Tâches asynchrones du domaine e-learning."""

import json
import logging
import subprocess  # noqa: S404 — appel maîtrisé à ffprobe, sans shell

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name="elearning.preparer_video")
def preparer_video(video_id: str) -> str:
    """Extrait les métadonnées d'une vidéo déposée et la rend publiable.

    V1 : durée et vérification de présence du fichier. Le transcodage en flux
    segmenté est prévu en V2 et ne touchera que cette tâche (ADR-001).
    """
    from apps.elearning.models import VideoAsset

    video = VideoAsset.objects.filter(pk=video_id).first()
    if video is None:
        logger.warning("Vidéo %s introuvable", video_id)
        return "introuvable"

    video.statut_traitement = VideoAsset.StatutTraitement.EN_COURS
    video.save(update_fields=["statut_traitement", "updated_at"])

    try:
        duree = _duree_secondes(video)
        if duree:
            video.duree_secondes = duree
        video.statut_traitement = VideoAsset.StatutTraitement.PRET
        video.message_erreur = ""
        video.save(update_fields=["duree_secondes", "statut_traitement", "message_erreur", "updated_at"])
    except Exception as erreur:  # noqa: BLE001
        logger.exception("Préparation de la vidéo %s en échec", video_id)
        video.statut_traitement = VideoAsset.StatutTraitement.ERREUR
        video.message_erreur = str(erreur)[:500]
        video.save(update_fields=["statut_traitement", "message_erreur", "updated_at"])
        return "erreur"

    # La durée du module dépend de celle de ses leçons.
    for lecon in video.lecons.select_related("chapitre__module"):
        if not lecon.duree_secondes:
            lecon.duree_secondes = video.duree_secondes
            lecon.save(update_fields=["duree_secondes", "updated_at"])
        lecon.chapitre.module.recalculer_duree()

    _notifier_depositaire(video)
    return "pret"


def _duree_secondes(video) -> int:
    """Durée lue par ffprobe. Retourne 0 si l'outil n'est pas disponible.

    L'absence de ffprobe ne doit pas bloquer la publication : la durée reste
    alors celle saisie par l'enseignant.
    """
    from apps.elearning.diffusion import LocalStockageVideo, stockage_video

    stockage = stockage_video()
    if not isinstance(stockage, LocalStockageVideo):
        return 0

    from django.core.files.storage import default_storage

    if not default_storage.exists(video.cle_stockage):
        raise FileNotFoundError(f"Fichier absent : {video.cle_stockage}")

    chemin = default_storage.path(video.cle_stockage)
    try:
        # ffprobe est résolu via le PATH : son emplacement varie selon l'image
        # (Debian, Alpine). L'absence de l'outil est traitée plus bas.
        sortie = subprocess.run(  # noqa: S603 — arguments fixes, aucun shell
            [  # noqa: S607 — ffprobe est résolu via le PATH, cf. commentaire ci-dessus
                "ffprobe",
                "-v",
                "quiet",
                "-print_format",
                "json",
                "-show_format",
                chemin,
            ],
            capture_output=True,
            text=True,
            timeout=60,
            check=True,
        )
        return int(float(json.loads(sortie.stdout)["format"]["duration"]))
    except (FileNotFoundError, subprocess.SubprocessError, KeyError, ValueError):
        logger.info("ffprobe indisponible ou illisible : durée laissée à la saisie manuelle")
        return 0


def _notifier_depositaire(video) -> None:
    from apps.core.models import Notification
    from apps.core.services.notifications import notifier

    notifier(
        video.uploade_par,
        f"Vidéo prête — {video.titre}",
        type_notification=Notification.Type.SYSTEME,
        message=(
            f"La vidéo « {video.titre} » que vous aviez déposée a fini d'être préparée. "
            "Elle est lisible dans l'atelier, et le module qui la contient peut désormais être publié."
        ),
        details=[
            {"libelle": "Vidéo", "valeur": video.titre},
            {"libelle": "État", "valeur": video.get_statut_traitement_display()},
        ],
    )


@shared_task(name="elearning.expirer_acces")
def expirer_acces() -> int:
    from apps.elearning.services.octroi import expirer_acces_echus

    nombre = expirer_acces_echus()
    logger.info("Accès expirés : %s", nombre)
    return nombre


@shared_task(name="elearning.generer_attestation_pdf")
def generer_attestation_pdf(attestation_id: str) -> str:
    """Rend l'attestation en PDF et l'attache à l'enregistrement."""
    from django.core.files.base import ContentFile

    from apps.elearning.models import AttestationModule

    attestation = (
        AttestationModule.objects.filter(pk=attestation_id)
        .select_related("inscription__module", "inscription__etudiant__utilisateur")
        .first()
    )
    if attestation is None:
        return "introuvable"
    if attestation.fichier_pdf:
        return "deja_generee"

    from django.conf import settings

    from apps.core.services.pdf import MoteurPDFIndisponible, contexte_marque, qr_data_uri, rendre_pdf
    from apps.documents.services_generation import obtenir_signature_secretariat_data_uri

    adresse = f"{getattr(settings, 'SITE_URL', '').rstrip('/')}{attestation.url_verification()}"
    signature_pdf, secretariat_nom, secretariat_qualite = obtenir_signature_secretariat_data_uri()
    try:
        pdf = rendre_pdf(
            "elearning/attestation_pdf.html",
            contexte_marque(
                attestation=attestation,
                qr_verification=qr_data_uri(adresse),
                signature_pdf=signature_pdf,
                secretariat_nom=secretariat_nom,
                secretariat_qualite=secretariat_qualite,
            ),
        )
    except MoteurPDFIndisponible:
        logger.warning("WeasyPrint indisponible : attestation %s sans PDF", attestation_id)
        return "sans_pdf"
    attestation.fichier_pdf.save(f"{attestation.numero}.pdf", ContentFile(pdf), save=True)
    return "generee"
