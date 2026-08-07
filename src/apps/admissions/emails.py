"""Service d'envoi d'emails pour les admissions — CDC §7.1."""

from django.conf import settings
from django.urls import reverse

from apps.core.services.emails import envoyer_notification_email


def _url_suivi(dossier):
    return f"{settings.SITE_URL}{reverse('admissions:candidature_suivi', kwargs={'token': dossier.token_suivi})}"


def send_candidature_confirmation(dossier):
    suivi_url = _url_suivi(dossier)
    envoyer_notification_email(
        sujet="Votre candidature a bien été enregistrée",
        titre="Votre candidature a bien été enregistrée",
        message=(
            f"Bonjour {dossier.prenom},\n\n"
            f"Nous avons bien reçu votre candidature pour le parcours « {dossier.parcours_souhaite} ».\n\n"
            f"Votre dossier est en cours d'examen. Vous pouvez suivre son avancement "
            f"à tout moment depuis votre page de suivi.\n\n"
            f"Nous reviendrons vers vous dans les meilleurs délais.\n\n"
            f"Cordialement,\nLe secrétariat de l'ITEAG"
        ),
        lien=suivi_url,
        libelle_lien="Suivre ma candidature",
        destinataires=[dossier.email],
    )


def send_statut_change_email(dossier):
    from .models import DossierCandidature

    suivi_url = _url_suivi(dossier)
    subject_map = {
        DossierCandidature.Statut.EN_EXAMEN: None,
        DossierCandidature.Statut.INCOMPLET: "ITEAG — Votre dossier est incomplet",
        DossierCandidature.Statut.ACCEPTE: "ITEAG — Votre candidature est acceptée",
        DossierCandidature.Statut.REFUSE: "ITEAG — Réponse à votre candidature",
    }
    body_map = {
        DossierCandidature.Statut.INCOMPLET: (
            f"Bonjour {dossier.prenom},\n\n"
            f"Après examen de votre dossier, certains éléments sont manquants ou à compléter :\n\n"
            f"{dossier.elements_manquants or 'Veuillez nous contacter pour plus de détails.'}\n\n"
            f"Vous pouvez suivre l'état de votre dossier ici :\n{suivi_url}\n\n"
            f"Cordialement,\nLe secrétariat de l'ITEAG"
        ),
        DossierCandidature.Statut.ACCEPTE: (
            f"Bonjour {dossier.prenom},\n\n"
            f"Nous avons le plaisir de vous informer que votre candidature "
            f"pour le parcours « {dossier.parcours_souhaite} » a été acceptée.\n\n"
            f"Vous recevrez prochainement les instructions pour finaliser votre inscription.\n\n"
            f"Cordialement,\nLe secrétariat de l'ITEAG"
        ),
        DossierCandidature.Statut.REFUSE: (
            f"Bonjour {dossier.prenom},\n\n"
            f"Après examen attentif de votre dossier, nous ne sommes malheureusement "
            f"pas en mesure de donner une suite favorable à votre candidature.\n\n"
            f"{('Motif : ' + dossier.motif_refus + chr(10) + chr(10)) if dossier.motif_refus else ''}"
            f"N'hésitez pas à nous contacter pour toute question.\n\n"
            f"Cordialement,\nLe secrétariat de l'ITEAG"
        ),
    }
    subject = subject_map.get(dossier.statut)
    if not subject:
        return
    envoyer_notification_email(
        sujet=subject.removeprefix("ITEAG — "),
        titre=subject.removeprefix("ITEAG — "),
        message=body_map.get(dossier.statut, ""),
        lien=suivi_url,
        libelle_lien="Suivre ma candidature",
        destinataires=[dossier.email],
    )


def envoyer_demande_de_pieces(demande):
    """Un seul message pour le lot ; le texte commun n'est jamais répété."""
    dossier = demande.dossier
    pieces = list(demande.pieces.all())
    liste = "\n".join(
        f"  - {piece.libelle}" + (f"\n      {piece.precisions}" if piece.precisions else "") for piece in pieces
    )
    message_commun = f"Message du secrétariat :\n{demande.message}\n\n" if demande.message.strip() else ""
    echeance = (
        f"Ces documents sont attendus avant le {demande.date_limite:%d/%m/%Y}.\n\n" if demande.date_limite else ""
    )
    envoyer_notification_email(
        sujet="Pièces à fournir pour votre dossier",
        titre="Pièces à fournir pour votre dossier",
        message=(
            f"Bonjour {dossier.prenom},\n\n"
            f"Pour finaliser votre dossier, le secrétariat vous demande de transmettre "
            f"{'le document suivant' if len(pieces) == 1 else 'les documents suivants'} :\n\n"
            f"{message_commun}{liste}\n\n{echeance}"
            f"Déposez l'ensemble des documents attendus depuis votre page de suivi, "
            f"puis envoyez-les en une seule fois.\n\n"
            f"Cordialement,\nLe secrétariat de l'ITEAG"
        ),
        lien=_url_suivi(dossier),
        libelle_lien="Déposer les documents",
        destinataires=[dossier.email],
    )


def envoyer_confirmation_depot_pieces(demande, pieces):
    dossier = demande.dossier
    noms = "\n".join(f"  - {piece.libelle}" for piece in pieces)
    envoyer_notification_email(
        sujet="Vos documents ont bien été reçus",
        titre="Vos documents ont bien été reçus",
        message=(
            f"Bonjour {dossier.prenom},\n\n"
            f"Nous avons bien reçu votre envoi :\n\n{noms}\n\n"
            f"Le secrétariat va vérifier l'ensemble de la demande. Vous recevrez une seule "
            f"réponse récapitulative.\n\n"
            f"Cordialement,\nLe secrétariat de l'ITEAG"
        ),
        lien=_url_suivi(dossier),
        libelle_lien="Suivre mon dossier",
        destinataires=[dossier.email],
    )


def envoyer_decision_pieces(demande, validees, refusees):
    """Une décision et un courriel pour tout le lot, même en cas de refus partiel."""
    dossier = demande.dossier
    blocs = []
    if validees:
        blocs.append("Documents validés :\n" + "\n".join(f"  - {piece.libelle}" for piece in validees))
    if refusees:
        blocs.append(
            "Documents à refournir :\n" + "\n".join(f"  - {piece.libelle} : {piece.motif_refus}" for piece in refusees)
        )
    conclusion = (
        "Déposez ensemble les documents à corriger depuis votre page de suivi."
        if refusees
        else "L'ensemble des documents de cette demande est validé."
    )
    envoyer_notification_email(
        sujet="Vérification de vos pièces justificatives",
        titre="Vérification de vos pièces justificatives",
        message=(
            f"Bonjour {dossier.prenom},\n\n"
            f"Le secrétariat a terminé la vérification de votre envoi.\n\n"
            f"{chr(10).join(blocs)}\n\n{conclusion}\n\n"
            f"Cordialement,\nLe secrétariat de l'ITEAG"
        ),
        lien=_url_suivi(dossier),
        libelle_lien="Consulter la demande",
        destinataires=[dossier.email],
    )


def envoyer_refus_de_piece(piece):
    """Compatibilité avec une ancienne pièce non rattachée à un lot."""
    dossier = piece.dossier
    envoyer_notification_email(
        sujet=f"La pièce « {piece.libelle} » est à refournir",
        titre=f"La pièce « {piece.libelle} » est à refournir",
        message=(
            f"Bonjour {dossier.prenom},\n\n"
            f"Le document déposé pour « {piece.libelle} » n'a pas pu être retenu.\n\n"
            f"Motif : {piece.motif_refus}\n\n"
            f"Vous pouvez en déposer un nouveau depuis votre page de suivi.\n\n"
            f"Cordialement,\nLe secrétariat de l'ITEAG"
        ),
        lien=_url_suivi(dossier),
        libelle_lien="Déposer une nouvelle pièce",
        destinataires=[dossier.email],
    )
