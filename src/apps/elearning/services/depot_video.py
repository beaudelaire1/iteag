"""
Le dépôt d'un fichier vidéo par un enseignant, et ce qu'il devient si Bunny
refuse de le prendre.

Le chemin nominal reste celui de l'ADR-005 : la vidéo est déclarée chez Bunny,
poussée par le worker, puis effacée d'ici. L'institut convoie, il n'héberge pas.

Ce module ajoute la seule chose qui manquait à cette décision : que faire quand
Bunny n'accepte pas. Jusqu'ici, rien — le formulaire refusait la leçon, et
l'enseignant restait devant un message qui nommait une variable d'environnement
qu'il n'a aucun moyen de changer. Une clé mal recopiée suffisait donc à fermer
la création de cours à tout l'institut, sans que personne d'autre que
l'exploitant puisse débloquer quoi que ce soit.

Le repli garde le fichier sur le stockage de l'institut et le sert par la vue
d'adresse signée qui existe déjà. Ce n'est pas le chemin qu'on veut à demeure —
les octets repassent par l'application à chaque lecture, ce que Bunny évite —
mais c'est un chemin qui marche, dont la protection est celle qu'exige un module
restreint : une adresse signée, courte, révocable. Un cours déposé pendant la
panne reste lisible ; la panne, elle, se répare sans rien perdre.

La bascule se voit : l'enseignant est prévenu que sa vidéo est hébergée ici, et
l'exploitant trouve dans le journal la raison exacte du refus de Bunny.
"""

import logging

from apps.elearning.diffusion import LocalStockageVideo, nouvelle_cle

logger = logging.getLogger(__name__)

BUNNY = "bunny"
ITEAG = LocalStockageVideo.nom


def deposer(fichier, titre: str, enseignant) -> tuple[object, str]:
    """Crée la vidéo à partir du fichier remis, et dit qui l'héberge.

    Retourne la fiche créée et le nom de l'hébergeur retenu — « bunny » quand
    la déclaration a été acceptée, « local » quand elle ne l'a pas été.
    """
    from apps.elearning import bunny_televersement as bunny
    from apps.elearning.models import VideoAsset
    from apps.elearning.tasks import televerser_video_bunny

    titre = (titre or getattr(fichier, "name", "") or "Vidéo")[:250]

    try:
        identifiant = bunny.creer_video(titre)
    except bunny.TeleversementBunnyIndisponible as erreur:
        logger.error("Dépôt Bunny refusé, repli sur l'hébergement ITEAG : %s", erreur)
        return _heberger_ici(fichier, titre, enseignant), ITEAG

    video = VideoAsset.objects.create(
        titre=titre,
        cle_stockage=identifiant,
        fournisseur=BUNNY,
        fichier_source=fichier,
        nom_origine=(getattr(fichier, "name", "") or "")[:250],
        uploade_par=enseignant,
        statut_traitement=VideoAsset.StatutTraitement.EN_ATTENTE,
    )
    televerser_video_bunny.delay(str(video.pk))
    return video, BUNNY


def _heberger_ici(fichier, titre: str, enseignant):
    """Range le fichier sur le stockage de l'institut, sous une clé opaque.

    La vidéo est déclarée prête sans attendre : il n'y a pas d'encodage à
    surveiller, le fichier est servi tel qu'il a été déposé. Sa durée reste à
    zéro — l'écran de la leçon la demande de toute façon en minutes, et deviner
    ici obligerait à disposer de « ffprobe » dans l'image, ce qui ferait échouer
    le repli exactement là où il doit tenir.
    """
    from apps.elearning.models import VideoAsset

    nom = getattr(fichier, "name", "") or "video.mp4"
    cle_reelle = _copier_sur_stockage_iteag(fichier, nom)

    return VideoAsset.objects.create(
        titre=titre,
        cle_stockage=cle_reelle,
        fournisseur=ITEAG,
        nom_origine=nom[:250],
        taille_octets=getattr(fichier, "size", 0) or 0,
        uploade_par=enseignant,
        statut_traitement=VideoAsset.StatutTraitement.PRET,
    )


def _copier_sur_stockage_iteag(fichier, nom: str) -> str:
    """Copie un flux sur le stockage privé utilisé pour le repli ITEAG."""
    cle = nouvelle_cle(nom or "video.mp4")
    if hasattr(fichier, "seek"):
        fichier.seek(0)
    return LocalStockageVideo().televerser(fichier, cle) or cle


def basculer_bunny_en_iteag(video, *, raison: str = ""):
    """Transforme en place une vidéo Bunny non envoyée en vidéo locale prête.

    La fiche existe déjà et peut être rattachée à une leçon. Créer une seconde
    VideoAsset casserait ce rattachement ; on conserve donc la même fiche, on
    copie son fichier temporaire sous une clé de lecture privée, puis on retire
    le dépôt temporaire.
    """
    from apps.elearning.models import VideoAsset

    if video.fournisseur != BUNNY:
        return video
    if not video.fichier_source:
        raise RuntimeError("Aucun fichier source n'est disponible pour le repli ITEAG.")

    nom = video.nom_origine or getattr(video.fichier_source, "name", "") or "video.mp4"
    taille = video.fichier_source.size
    with video.fichier_source.open("rb") as fichier:
        cle_reelle = _copier_sur_stockage_iteag(fichier, nom)

    # La copie locale est désormais la source de lecture. Le dépôt temporaire
    # n'a plus de rôle et peut être supprimé sans toucher à la nouvelle clé.
    video.fichier_source.delete(save=False)
    video.fichier_source = ""
    video.cle_stockage = cle_reelle
    video.fournisseur = ITEAG
    video.taille_octets = taille
    video.statut_traitement = VideoAsset.StatutTraitement.PRET
    video.message_erreur = ""
    video.save(
        update_fields=[
            "fichier_source",
            "cle_stockage",
            "fournisseur",
            "taille_octets",
            "statut_traitement",
            "message_erreur",
            "updated_at",
        ]
    )
    logger.warning(
        "Vidéo %s basculée sur l'hébergement ITEAG après indisponibilité Bunny%s",
        video.pk,
        f" : {raison}" if raison else "",
    )
    return video


MESSAGE_REPLI = (
    "Bunny n'a pas pu prendre le dépôt : la vidéo est donc hébergée par ITEAG. "
    "Elle est lisible dès maintenant, et le restera. Signalez-le à "
    "l'administrateur du site, qui pourra la basculer chez Bunny lorsque le "
    "service sera de nouveau disponible ou la configuration corrigée."
)
