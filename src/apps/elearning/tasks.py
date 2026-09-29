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


@shared_task(name="elearning.televerser_video_bunny", bind=True, max_retries=2)
def televerser_video_bunny(self, video_id: str) -> str:
    """Pousse le fichier chez Bunny, puis confie le suivi à une autre tâche.

    L'envoi du fichier occupe réellement le worker et doit donc rester ici. En
    revanche, l'encodage se déroule chez Bunny : attendre en boucle dans Celery
    immobiliserait un processus pour ne rien faire. Une tâche courte de suivi
    est planifiée après l'envoi et se reprogramme elle-même tant que nécessaire.
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
    except bunny.TeleversementBunnyTemporairementIndisponible as erreur:
        if self.request.retries < self.max_retries:
            delais = (30, 120)
            delai = delais[min(self.request.retries, len(delais) - 1)]
            logger.warning(
                "Bunny temporairement indisponible pour la vidéo %s ; nouvelle tentative dans %ss (%s/%s)",
                video_id,
                delai,
                self.request.retries + 1,
                self.max_retries,
            )
            raise self.retry(exc=erreur, countdown=delai)

        from apps.elearning.services.depot_video import basculer_bunny_en_iteag

        try:
            basculer_bunny_en_iteag(video, raison=str(erreur))
        except Exception as erreur_repli:  # noqa: BLE001
            logger.exception("Repli ITEAG impossible pour la vidéo %s", video_id)
            video.statut_traitement = VideoAsset.StatutTraitement.ERREUR
            video.message_erreur = (
                f"Bunny reste indisponible et le repli ITEAG a échoué : {erreur_repli}"
            )[:500]
            video.save(update_fields=["statut_traitement", "message_erreur", "updated_at"])
            return "erreur"

        _notifier_depositaire(video)
        return "pret_local"
    except Exception as erreur:  # noqa: BLE001
        logger.exception("Téléversement Bunny en échec pour la vidéo %s", video_id)
        video.statut_traitement = VideoAsset.StatutTraitement.ERREUR
        video.message_erreur = str(erreur)[:500]
        video.save(update_fields=["statut_traitement", "message_erreur", "updated_at"])
        return "erreur"

    # Persiste le fait que le fichier a bien quitté ITEAG avant de rendre le
    # worker. Ce marqueur permet aussi de distinguer un dépôt déjà envoyé d'un
    # dépôt qui doit réellement être retransmis après incident.
    video.taille_octets = taille
    video.save(update_fields=["taille_octets", "updated_at"])
    verifier_encodage_bunny.apply_async(args=[video_id, 0], countdown=5)
    return "envoyee"


DELAI_VERIFICATION_BUNNY_SECONDES = 10
MAX_VERIFICATIONS_BUNNY = 120  # 20 minutes sans immobiliser un worker


@shared_task(name="elearning.verifier_encodage_bunny")
def verifier_encodage_bunny(video_id: str, tentative: int = 0) -> str:
    """Contrôle une fois l'encodage Bunny, puis rend immédiatement le worker."""

    from apps.elearning import bunny_televersement as bunny
    from apps.elearning.models import VideoAsset

    video = VideoAsset.objects.filter(pk=video_id).first()
    if video is None:
        return "introuvable"
    if video.fournisseur != "bunny":
        return "autre_fournisseur"
    if video.statut_traitement == VideoAsset.StatutTraitement.PRET:
        return "pret"

    try:
        etat = bunny.etat_video(video.cle_stockage)
    except bunny.TeleversementBunnyTemporairementIndisponible as erreur:
        logger.warning("État Bunny momentanément indisponible pour %s : %s", video.pk, erreur)
        return _reprogrammer_verification_bunny(video, tentative)
    except Exception as erreur:  # noqa: BLE001
        logger.exception("Lecture de l'état Bunny impossible pour la vidéo %s", video_id)
        video.statut_traitement = VideoAsset.StatutTraitement.ERREUR
        video.message_erreur = str(erreur)[:500]
        video.save(update_fields=["statut_traitement", "message_erreur", "updated_at"])
        return "erreur"

    if etat in (bunny.ETAT_TERMINE, bunny.ETAT_RESOLUTION_TERMINEE):
        try:
            video.duree_secondes = bunny.duree_video(video.cle_stockage) or video.duree_secondes
        except bunny.TeleversementBunnyTemporairementIndisponible:
            # La vidéo est déjà lisible. Une durée temporairement indisponible
            # ne doit pas retarder sa publication.
            logger.warning("Durée Bunny momentanément indisponible pour %s", video.pk)
        _finaliser_video_bunny(video)
        return "pret"

    if etat in bunny.ETATS_ECHEC:
        video.statut_traitement = VideoAsset.StatutTraitement.ERREUR
        video.message_erreur = "Bunny a rejeté la vidéo : format illisible ou transfert interrompu."
        video.save(update_fields=["statut_traitement", "message_erreur", "updated_at"])
        return "erreur"

    return _reprogrammer_verification_bunny(video, tentative)


def _reprogrammer_verification_bunny(video, tentative: int) -> str:
    """Planifie le prochain contrôle sans dormir dans un processus Celery."""
    from django.conf import settings

    from apps.elearning.models import VideoAsset

    if tentative + 1 >= MAX_VERIFICATIONS_BUNNY:
        video.statut_traitement = VideoAsset.StatutTraitement.ERREUR
        video.message_erreur = (
            "Bunny n'a pas terminé l'encodage dans le délai prévu. "
            "Le fichier source est conservé et l'envoi peut être relancé."
        )
        video.save(update_fields=["statut_traitement", "message_erreur", "updated_at"])
        return "delai_depasse"

    # Sert aussi de heartbeat : la tâche de récupération ne doit relancer que
    # les vidéos dont le suivi s'est réellement interrompu.
    video.save(update_fields=["updated_at"])

    # En test et en développement eager, Celery ignore le countdown et exécute
    # immédiatement la tâche suivante. Se reprogrammer créerait alors une
    # récursion de 120 appels. La production n'utilise jamais ce mode.
    if settings.CELERY_TASK_ALWAYS_EAGER:
        return "en_attente"

    verifier_encodage_bunny.apply_async(
        args=[str(video.pk), tentative + 1],
        countdown=DELAI_VERIFICATION_BUNNY_SECONDES,
    )
    return "en_attente"


def _finaliser_video_bunny(video) -> None:
    """Marque prête une vidéo Bunny devenue lisible et libère le dépôt source."""
    from apps.elearning.models import VideoAsset

    if video.fichier_source:
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


@shared_task(name="elearning.recuperer_videos_bunny_en_cours")
def recuperer_videos_bunny_en_cours(age_secondes: int = 45) -> int:
    """Relance le suivi des vidéos abandonnées par un redémarrage du worker.

    Une tâche de suivi normale rafraîchit updated_at à chaque passage. Une
    vidéo en_cours dont ce timestamp est ancien n’est donc pas simplement
    lente : plus personne ne la surveille. Beat remet uniquement ces fiches en
    file, ce qui rend un redéploiement sans conséquence pour un encodage Bunny.
    """
    from apps.elearning.models import VideoAsset

    limite = timezone.now() - timedelta(seconds=age_secondes)
    identifiants = list(
        VideoAsset.objects.filter(
            fournisseur="bunny",
            statut_traitement=VideoAsset.StatutTraitement.EN_COURS,
            updated_at__lt=limite,
        )
        .order_by("updated_at")
        .values_list("pk", flat=True)[:50]
    )
    if not identifiants:
        return 0

    # Réserve ces fiches avant de publier les tâches : le prochain passage de
    # Beat ne doit pas les remettre une seconde fois en file.
    VideoAsset.objects.filter(pk__in=identifiants).update(updated_at=timezone.now())
    for identifiant in identifiants:
        verifier_encodage_bunny.delay(str(identifiant))
    return len(identifiants)


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
