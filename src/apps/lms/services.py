"""
Règles de gestion du travail demandé et de sa correction.

Elles vivent ici plutôt que dans les vues pour deux raisons : elles sont
partagées entre le portail enseignant et le portail étudiant, et elles se
testent sans passer par une requête HTTP.
"""

from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.core.models import Notification
from apps.core.services.audit import journaliser
from apps.core.services.notifications import notifier

from .models import Devoir, Evaluation, ReponseEtudiant, RevisionNote

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
    inscrits = list(devoir.inscriptions_destinataires())
    if not inscrits:
        if devoir.portee == Devoir.Portee.COURS:
            raise ValidationError("Aucun étudiant n'est inscrit à ce cours : le devoir n'aurait aucun destinataire.")
        raise ValidationError(
            f"{devoir.libelle_destinataires} ne recouvre aucun inscrit de ce cours : "
            "le devoir n'aurait aucun destinataire."
        )

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
                    f"Un travail vous est demandé pour le cours « {devoir.cours_session.cours.titre} ». "
                    "Vous pouvez consulter la consigne et déposer votre copie depuis votre espace étudiant, "
                    "jusqu'à la date de remise indiquée ci-dessous."
                ),
                details=_details_devoir(devoir),
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
    cours = evaluation.cours_session.cours.titre
    notifier(
        evaluation.etudiant.utilisateur,
        f"Délai accordé — {cours}",
        message=(
            f"Votre enseignant vous accorde un délai supplémentaire pour remettre votre travail "
            f"du cours « {cours} ». Aucune démarche n'est nécessaire : le dépôt reste ouvert dans "
            "votre espace jusqu'à la nouvelle échéance."
        ),
        details=[
            {"libelle": "Cours", "valeur": cours},
            {"libelle": "Nouvelle échéance", "valeur": f"{timezone.localtime(jusqu_au):%d/%m/%Y à %H:%M}"},
        ],
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
    _avertir_de_la_remise(evaluation)
    return evaluation


def _avertir_de_la_remise(evaluation) -> None:
    """Accuse réception à l'étudiant, et signale la copie au secrétariat.

    L'étudiant déposait sans rien recevoir en retour : il ne savait pas si son
    fichier était arrivé. Le secrétariat, lui, ne l'apprenait jamais — or c'est
    lui qui relancera l'enseignant si la copie reste sans note.
    """
    from django.contrib.auth import get_user_model
    from django.urls import reverse

    from apps.core.models import Notification
    from apps.core.services.notifications import notifier, notifier_plusieurs

    cours = evaluation.cours_session
    details = [
        {"libelle": "Cours", "valeur": cours.cours.titre},
        {"libelle": "Étudiant", "valeur": str(evaluation.etudiant)},
        {"libelle": "Remise", "valeur": "en retard" if evaluation.depot_tardif else "dans les délais"},
    ]

    notifier(
        evaluation.etudiant.utilisateur,
        f"Devoir remis — {cours.cours.titre}",
        type_notification=Notification.Type.SYSTEME,
        message=(
            "Votre copie est bien arrivée. Vous serez prévenu dès que votre note "
            "sera publiée."
        ),
        details=details,
    )

    User = get_user_model()
    notifier_plusieurs(
        User.objects.filter(is_active=True, role=User.Role.SECRETARIAT),
        f"Copie remise — {evaluation.etudiant}",
        type_notification=Notification.Type.SYSTEME,
        message=(
            f"Une copie vient d'être remise pour « {cours.cours.titre} ». "
            "Elle apparaîtra dans le suivi des corrections."
        ),
        details=details,
        url_cible=reverse("administration:corrections"),
    )


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
    cours = evaluation.cours_session.cours.titre
    notifier(
        evaluation.etudiant.utilisateur,
        f"Note révisée — {cours}",
        type_notification=Notification.Type.NOTE_PUBLIEE,
        message=(
            f"Votre note pour le cours « {cours} » a été révisée par votre enseignant. "
            "La note précédente est conservée dans votre dossier : les deux valeurs, ainsi que "
            "le motif de la révision, sont consultables dans votre espace étudiant."
        ),
        details=[
            {"libelle": "Cours", "valeur": cours},
            {"libelle": "Motif de la révision", "valeur": revision.motif},
        ],
        url_cible="/espace-etudiant/notes/",
    )
    return revision


# ──────────────────────────────────────────────
# Questionnaires
# ──────────────────────────────────────────────


MOTIF_RECORRECTION = "Recorrection après modification du barème."


def _details_devoir(devoir: Devoir) -> list[dict]:
    """Les faits d'un devoir, tels qu'ils figurent dans le courriel.

    Une échéance dans un tableau se retrouve ; noyée dans une phrase, elle se
    relit trois fois. C'est la seule information que l'étudiant cherche
    vraiment en ouvrant l'avis.
    """
    details = [
        {"libelle": "Devoir", "valeur": devoir.titre},
        {"libelle": "Cours", "valeur": devoir.cours_session.cours.titre},
        {"libelle": "Modalité", "valeur": devoir.get_modalite_display()},
        {
            "libelle": "À remettre avant le",
            "valeur": f"{timezone.localtime(devoir.date_fermeture):%d/%m/%Y à %H:%M}",
        },
    ]
    if devoir.bareme:
        details.append({"libelle": "Barème", "valeur": f"{devoir.bareme:g} points"})
    return details


def _appreciation_qcm(obtenus: Decimal, total_points: Decimal) -> str:
    """Le détail chiffré qui accompagne la note d'un questionnaire.

    Écrit une fois : la note et l'appréciation sont produites au même endroit à
    la remise comme à la recorrection, ce qui interdit qu'elles se contredisent.
    """
    return f"Questionnaire corrigé automatiquement : {obtenus} / {total_points} points."


def motif_qcm_incomplet(devoir: Devoir) -> str:
    """Ce qui empêche d'ouvrir ce questionnaire — vide s'il est prêt.

    Contrôlé à l'ouverture et non à la saisie : une question se construit en
    plusieurs fois, et refuser d'enregistrer une question sans propositions
    interdirait d'en écrire l'énoncé avant d'y penser.
    """
    if devoir.modalite != Devoir.Modalite.QCM:
        return ""

    questions = list(devoir.questions.prefetch_related("choix"))
    if not questions:
        return "Ce questionnaire ne contient aucune question."

    for rang, question in enumerate(questions, start=1):
        probleme = question.est_valide()
        if probleme:
            return f"Question {rang} : {probleme}"
    return ""


@transaction.atomic
def enregistrer_reponses(evaluation: Evaluation, choix_par_question: dict) -> Evaluation:
    """Enregistre les réponses d'un étudiant, corrige, et note.

    La correction est immédiate parce qu'elle est mécanique : un questionnaire à
    propositions fermées n'attend l'avis de personne. L'enseignant garde la main
    ensuite — la note reste révisable, et la copie n'est pas publiée d'office.
    """
    motif = evaluation.motif_de_refus_depot()
    if motif:
        raise ValidationError(motif)

    devoir = evaluation.devoir
    if devoir is None or devoir.modalite != Devoir.Modalite.QCM:
        raise ValidationError("Ce devoir n'est pas un questionnaire.")

    questions = list(devoir.questions.prefetch_related("choix"))
    total_points = sum((question.points for question in questions), Decimal("0"))
    if total_points <= 0:
        raise ValidationError("Ce questionnaire ne vaut aucun point : il ne peut pas être noté.")

    obtenus = Decimal("0")
    for question in questions:
        reponse, _ = ReponseEtudiant.objects.get_or_create(evaluation=evaluation, question=question)
        # Seules les propositions de la question comptent : un identifiant
        # étranger glissé dans la requête ne peut pas rapporter de point.
        retenus = question.choix.filter(pk__in=choix_par_question.get(question.pk, []))
        reponse.choix.set(retenus)
        obtenus += reponse.corriger()
        reponse.save(update_fields=["points_obtenus", "updated_at"])

    note = (obtenus / total_points * devoir.bareme).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    evaluation.note = note
    evaluation.statut = Evaluation.StatutEvaluation.NOTE
    evaluation.date_soumission = timezone.now()
    evaluation.date_notation = timezone.now()
    evaluation.depot_tardif = bool(evaluation.echeance() and evaluation.date_soumission > evaluation.echeance())
    evaluation.appreciation = _appreciation_qcm(obtenus, total_points)
    evaluation.save(
        update_fields=[
            "note",
            "statut",
            "date_soumission",
            "date_notation",
            "depot_tardif",
            "appreciation",
            "updated_at",
        ]
    )
    return evaluation


@transaction.atomic
def recorriger(devoir: Devoir, *, par=None) -> int:
    """Rejoue la correction de toutes les copies d'un questionnaire.

    Sert lorsqu'un barème est rectifié après coup — question retirée, seconde
    bonne réponse admise. Les réponses des étudiants sont conservées telles
    quelles, ce qui rend l'opération possible sans redemander quoi que ce soit.

    Une copie déjà publiée n'est pas réécrite en silence : elle passe par la
    révision, qui conserve l'ancienne note, porte un motif et avertit
    l'étudiant. Sans cela, une note rendue changeait sans que personne ne
    puisse dire ce qu'elle valait la veille ni pourquoi elle a bougé.
    """
    questions = list(devoir.questions.prefetch_related("choix"))
    total_points = sum((question.points for question in questions), Decimal("0"))
    if total_points <= 0:
        return 0

    recorrigees = 0
    for copie in devoir.copies.exclude(statut=Evaluation.StatutEvaluation.EN_ATTENTE).prefetch_related(
        "reponses__choix", "reponses__question__choix"
    ):
        obtenus = sum((reponse.corriger() for reponse in copie.reponses.all()), Decimal("0"))
        for reponse in copie.reponses.all():
            reponse.save(update_fields=["points_obtenus", "updated_at"])

        note = (obtenus / total_points * devoir.bareme).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        appreciation = _appreciation_qcm(obtenus, total_points)

        if copie.est_publiee:
            # Une note publiée que le nouveau barème laisse inchangée n'a pas
            # été révisée : lui inventer une trace et en avertir l'étudiant
            # ferait du bruit là où rien n'a bougé.
            if copie.note != note:
                reviser(copie, note=note, motif=MOTIF_RECORRECTION, appreciation=appreciation, par=par)
        else:
            # Note, appréciation et date partent ensemble : la fiche affichait
            # la note recalculée à côté du détail chiffré de l'ancien barème.
            copie.note = note
            copie.appreciation = appreciation
            copie.date_notation = timezone.now()
            copie.save(update_fields=["note", "appreciation", "date_notation", "updated_at"])
        recorrigees += 1
    return recorrigees


# ──────────────────────────────────────────────
# Groupes
# ──────────────────────────────────────────────


def message_au_groupe(groupe, *, titre: str, message: str, par=None) -> int:
    """Notifie tous les membres d'un groupe. Retourne le nombre d'envois."""
    from apps.core.services.notifications import notifier_plusieurs

    destinataires = [membre.utilisateur for membre in groupe.membres.select_related("utilisateur")]
    envoyes = notifier_plusieurs(
        destinataires,
        titre,
        type_notification=Notification.Type.ANNONCE,
        message=message,
        # Le message est celui de l'enseignant ; les précisions disent à quel
        # titre l'étudiant le reçoit — un groupe de travail se confond
        # facilement avec un autre.
        details=[
            {"libelle": "Groupe", "valeur": groupe.nom},
            {"libelle": "Cours", "valeur": groupe.cours_session.cours.titre},
        ],
        url_cible="/espace-etudiant/cours/",
    )
    journaliser(
        "creation",
        utilisateur=par,
        objet=groupe,
        objet_libelle=f"Message au groupe « {groupe.nom} »",
        destinataires=envoyes,
    )
    return envoyes
