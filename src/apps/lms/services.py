"""
Règles de gestion du travail demandé et de sa correction.

Elles vivent ici plutôt que dans les vues pour deux raisons : elles sont
partagées entre le portail enseignant et le portail étudiant, et elles se
testent sans passer par une requête HTTP.
"""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.core.models import Notification
from apps.core.services.audit import journaliser
from apps.core.services.notifications import notifier

from .models import Devoir, Evaluation, RevisionNote

# ──────────────────────────────────────────────
# Ouverture d'un devoir
# ──────────────────────────────────────────────


@transaction.atomic
def publier_devoir(devoir: Devoir, *, par=None) -> Devoir:
    """Ouvre le devoir aux étudiants et crée une copie vide par inscrit.

    La copie est créée à la publication, et non au premier dépôt : c'est elle
    qui fait apparaître le devoir dans l'espace de l'étudiant. Sans cela, un
    étudiant qui ne dépose rien n'existe pas dans le suivi, et l'enseignant ne
    voit pas qui lui manque.
    """
    inscrits = list(devoir.cours_session.inscriptions.select_related("etudiant__utilisateur"))
    if not inscrits:
        raise ValidationError("Aucun étudiant n'est inscrit à ce cours : le devoir n'aurait aucun destinataire.")

    devoir.statut = Devoir.Statut.PUBLIE
    devoir.save(update_fields=["statut", "updated_at"])

    creees = 0
    for inscription in inscrits:
        _, creee = Evaluation.objects.get_or_create(
            cours_session=devoir.cours_session,
            etudiant=inscription.etudiant,
            devoir=devoir,
            defaults={
                "type_evaluation": devoir.type_evaluation,
                "statut": Evaluation.StatutEvaluation.EN_ATTENTE,
                "ects_valides": 0,
            },
        )
        creees += int(creee)
        if creee:
            notifier(
                inscription.etudiant.utilisateur,
                f"Nouveau devoir — {devoir.titre}",
                type_notification=Notification.Type.ANNONCE,
                message=(
                    f"À remettre avant le {timezone.localtime(devoir.date_fermeture):%d/%m/%Y à %H:%M} "
                    f"pour « {devoir.cours_session.cours.titre} »."
                ),
                url_cible="/espace-etudiant/notes/",
            )

    journaliser(
        "creation",
        utilisateur=par,
        objet=devoir,
        objet_libelle=f"Publication du devoir « {devoir.titre} »",
        copies_creees=creees,
    )
    return devoir


@transaction.atomic
def clore_devoir(devoir: Devoir, *, par=None) -> Devoir:
    """Ferme définitivement le dépôt, quelle que soit la date de fermeture."""
    devoir.statut = Devoir.Statut.CLOS
    devoir.save(update_fields=["statut", "updated_at"])
    journaliser("modification", utilisateur=par, objet=devoir, objet_libelle=f"Clôture du devoir « {devoir.titre} »")
    return devoir


def accorder_delai(evaluation: Evaluation, *, jusqu_au, par=None) -> Evaluation:
    """Repousse l'échéance pour un étudiant seul, sans toucher au devoir."""
    if jusqu_au <= timezone.now():
        raise ValidationError("Un délai se donne pour l'avenir.")

    evaluation.date_limite_reportee = jusqu_au
    evaluation.save(update_fields=["date_limite_reportee", "updated_at"])
    journaliser(
        "modification",
        utilisateur=par,
        objet=evaluation,
        objet_libelle=f"Délai accordé à {evaluation.etudiant}",
        jusqu_au=str(jusqu_au),
    )
    notifier(
        evaluation.etudiant.utilisateur,
        "Délai accordé",
        message=f"Vous pouvez remettre votre travail jusqu'au {timezone.localtime(jusqu_au):%d/%m/%Y à %H:%M}.",
        url_cible="/espace-etudiant/notes/",
    )
    return evaluation


# ──────────────────────────────────────────────
# Dépôt par l'étudiant
# ──────────────────────────────────────────────


@transaction.atomic
def deposer(evaluation: Evaluation, fichier, *, request=None) -> Evaluation:
    """Enregistre la remise d'un étudiant, si la fenêtre l'autorise.

    Le contrôle est refait ici et non dans la vue : la page a pu être ouverte
    avant la fermeture et soumise après.
    """
    motif = evaluation.motif_de_refus_depot()
    if motif:
        raise ValidationError(motif)

    echeance = evaluation.echeance()
    evaluation.fichier_soumis = fichier
    evaluation.statut = Evaluation.StatutEvaluation.SOUMIS
    evaluation.date_soumission = timezone.now()
    evaluation.depot_tardif = bool(echeance and evaluation.date_soumission > echeance)
    evaluation.save(update_fields=["fichier_soumis", "statut", "date_soumission", "depot_tardif", "updated_at"])

    journaliser(
        "creation",
        utilisateur=evaluation.etudiant.utilisateur,
        request=request,
        objet=evaluation,
        objet_libelle=f"Remise de {evaluation.etudiant}",
        tardif=evaluation.depot_tardif,
    )
    return evaluation


# ──────────────────────────────────────────────
# Notation et recours
# ──────────────────────────────────────────────


@transaction.atomic
def noter(evaluation: Evaluation, *, note, appreciation="", ects=None, par=None) -> Evaluation:
    """Enregistre une correction sur une copie qui n'est pas encore publiée."""
    if evaluation.est_publiee:
        raise ValidationError("Cette note est publiée : elle relève désormais de la procédure de révision.")

    evaluation.note = note
    evaluation.appreciation = appreciation
    if ects is not None:
        evaluation.ects_valides = ects
    evaluation.statut = Evaluation.StatutEvaluation.NOTE
    evaluation.date_notation = timezone.now()
    evaluation.save(update_fields=["note", "appreciation", "ects_valides", "statut", "date_notation", "updated_at"])
    return evaluation


@transaction.atomic
def reviser(evaluation: Evaluation, *, note, motif: str, appreciation=None, ects=None, par=None) -> RevisionNote:
    """Corrige une note déjà publiée, en conservant ce qu'elle valait avant.

    Le motif est obligatoire : une note qui change sans explication est
    inexploitable devant un étudiant qui conteste, et impossible à défendre
    devant un jury.
    """
    if not evaluation.est_publiee:
        raise ValidationError("La révision ne concerne que les notes déjà publiées.")
    if not motif.strip():
        raise ValidationError("Le motif de la révision est obligatoire.")

    revision = RevisionNote.objects.create(
        evaluation=evaluation,
        note_avant=evaluation.note,
        note_apres=note,
        appreciation_avant=evaluation.appreciation,
        motif=motif.strip(),
        auteur=par,
    )

    evaluation.note = note
    champs = ["note", "updated_at"]
    if appreciation is not None:
        evaluation.appreciation = appreciation
        champs.append("appreciation")
    if ects is not None:
        evaluation.ects_valides = ects
        champs.append("ects_valides")
    evaluation.save(update_fields=champs)

    journaliser(
        "modification",
        utilisateur=par,
        objet=evaluation,
        objet_libelle=f"Révision de note — {evaluation.etudiant}",
        note_avant=str(revision.note_avant),
        note_apres=str(revision.note_apres),
        motif=revision.motif,
    )
    notifier(
        evaluation.etudiant.utilisateur,
        f"Note révisée — {evaluation.cours_session.cours.titre}",
        type_notification=Notification.Type.NOTE_PUBLIEE,
        message=f"Votre note est passée de {revision.note_avant} à {revision.note_apres}. Motif : {revision.motif}",
        url_cible="/espace-etudiant/notes/",
    )
    return revision
