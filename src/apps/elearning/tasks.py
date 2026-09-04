"""Tâches asynchrones du domaine e-learning."""

import json
import logging
import subprocess  # noqa: S404 — appel maîtrisé à ffprobe, sans shell
from datetime import timedelta

from django.utils import timezone

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


@shared_task(name="elearning.televerser_video_bunny", bind=True, max_retries=0)
def televerser_video_bunny(self, video_id: str) -> str:
    """Pousse chez Bunny le fichier déposé, puis attend la fin de l'encodage.

    La vidéo est déjà déclarée chez le fournisseur au moment où cette tâche
    démarre : « cle_stockage » porte son identifiant. L'échec d'un envoi laisse
    donc une vidéo vide chez Bunny plutôt qu'un enregistrement orphelin ici, ce
    qui se répare en redéposant le fichier sur la même fiche.
    """
    from apps.elearning import bunny_televersement as bunny
    from apps.elearning.models import VideoAsset

    video = VideoAsset.objects.filter(pk=video_id).first()
    if video is None:
        logger.warning("Vidéo %s introuvable", video_id)
        return "introuvable"
    if not video.fichier_source:
        logger.warning("Vidéo %s sans fichier déposé", video_id)
        return "sans_fichier"

    video.statut_traitement = VideoAsset.StatutTraitement.EN_COURS
    video.message_erreur = ""
    video.save(update_fields=["statut_traitement", "message_erreur", "updated_at"])

    try:
        taille = video.fichier_source.size
        with video.fichier_source.open("rb") as fichier:
            bunny.envoyer_fichier(video.cle_stockage, fichier, taille)
        video.taille_octets = taille
        _attendre_encodage(video, bunny)
    except Exception as erreur:  # noqa: BLE001 — toute panne doit se lire sur la fiche
        logger.exception("Téléversement Bunny en échec pour la vidéo %s", video_id)
        video.statut_traitement = VideoAsset.StatutTraitement.ERREUR
        video.message_erreur = str(erreur)[:500]
        video.save(update_fields=["statut_traitement", "message_erreur", "updated_at"])
        return "erreur"

    # Le fichier a fait son office. Le garder ferait payer deux fois le même
    # octet — une fois chez Bunny, une fois sur R2 — sans que rien ne le lise.
    video.fichier_source.delete(save=False)
    video.statut_traitement = VideoAsset.StatutTraitement.PRET
    video.message_erreur = ""
    video.save(
        update_fields=[
            "fichier_source",
            "duree_secondes",
            "taille_octets",
            "statut_traitement",
            "message_erreur",
            "updated_at",
        ]
    )

    for lecon in video.lecons.select_related("chapitre__module"):
        if not lecon.duree_secondes:
            lecon.duree_secondes = video.duree_secondes
            lecon.save(update_fields=["duree_secondes", "updated_at"])
        lecon.chapitre.module.recalculer_duree()

    _notifier_depositaire(video)
    return "pret"


def _attendre_encodage(video, bunny, *, tentatives: int = 60, attente_secondes: int = 20) -> None:
    """Attend que Bunny déclare la vidéo lisible.

    Sans cette attente, la fiche annoncerait « prête » une vidéo encore en file
    d'attente : l'enseignant publierait son module et les étudiants tomberaient
    sur un lecteur vide. Vingt minutes de patience couvrent l'encodage d'une
    séquence longue ; au-delà, l'état reste « en préparation » et se rattrape
    en rouvrant la fiche.
    """
    import time

    for _ in range(tentatives):
        etat = bunny.etat_video(video.cle_stockage)
        if etat in (bunny.ETAT_TERMINE, bunny.ETAT_RESOLUTION_TERMINEE):
            video.duree_secondes = bunny.duree_video(video.cle_stockage) or video.duree_secondes
            return
        if etat == bunny.ETAT_ECHEC:
            raise RuntimeError("Bunny a rejeté la vidéo : format illisible ou transfert interrompu.")
        time.sleep(attente_secondes)

    raise TimeoutError("Bunny n'a pas fini d'encoder la vidéo dans le délai prévu.")


@shared_task(name="elearning.expirer_acces")
def expirer_acces() -> int:
    from apps.elearning.services.octroi import expirer_acces_echus

    nombre = expirer_acces_echus()
    logger.info("Accès expirés : %s", nombre)
    return nombre


@shared_task(name="elearning.purger_journal_acces")
def purger_journal_acces(jours: int | None = None) -> int:
    """Purge le journal d'accès vidéo au-delà de la durée de conservation.

    Cette table est la plus écrite du domaine — une ligne par demande de
    lecture, autorisée ou refusée — et chaque ligne porte une adresse IP
    nominative. Sans purge, elle croît sans borne et conserve indéfiniment des
    données que le registre annonce comme temporaires.

    La durée vit dans `RETENTION_JOURNAL_ACCES_VIDEO_JOURS`, justifiée au §3 bis
    du registre des traitements : la finalité codée — repérer un compte partagé
    — n'exploite qu'une fenêtre de quelques heures.
    """
    from django.conf import settings

    from apps.elearning.models import JournalAccesVideo

    if jours is None:
        jours = int(getattr(settings, "RETENTION_JOURNAL_ACCES_VIDEO_JOURS", 90))
    limite = timezone.now() - timedelta(days=jours)
    nombre, _ = JournalAccesVideo.objects.filter(created_at__lt=limite).delete()
    logger.info("Purge du journal d'accès vidéo : %s entrée(s) supprimée(s)", nombre)
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
    from apps.documents.services_generation import SignatureIllisible, obtenir_signature_secretariat_data_uri

    adresse = f"{getattr(settings, 'SITE_URL', '').rstrip('/')}{attestation.url_verification()}"
    try:
        signature_pdf, secretariat_nom, secretariat_qualite = obtenir_signature_secretariat_data_uri()
    except SignatureIllisible:
        # Une attestation porte le nom et la qualité du signataire : la produire
        # sans l'image de sa signature donnerait un document qui a l'air signé.
        # On préfère l'absence de PDF, réparable par une relance une fois le
        # stockage revenu, à une pièce trompeuse déjà remise à l'étudiant.
        logger.warning("Signature illisible : attestation %s laissée sans PDF", attestation_id)
        return "sans_pdf"
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
