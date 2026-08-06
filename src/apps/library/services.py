"""Workflows transactionnels pour les emprunts de la bibliothèque."""

from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.core.services.notifications import notifier
from apps.library.models import Emprunt, NoticeBibliographique, SuspensionBibliotheque


def _duree_suspension(jours_retard: int) -> int:
    """Un jour de retard vaut un jour de suspension, avec plafond configurable."""
    coefficient = max(1, int(getattr(settings, "LIBRARY_SUSPENSION_DAYS_PER_LATE_DAY", 1)))
    plafond = max(1, int(getattr(settings, "LIBRARY_SUSPENSION_MAX_DAYS", 30)))
    return min(jours_retard * coefficient, plafond)


def emprunt_en_retard_actif(emprunteur) -> Emprunt | None:
    """Détecte un retard même si la tâche planifiée n'a pas encore changé le statut."""
    return (
        Emprunt.objects.filter(
            emprunteur=emprunteur,
            statut__in=[Emprunt.Statut.EN_COURS, Emprunt.Statut.EN_RETARD],
            date_retour_effectif__isnull=True,
            date_retour_prevue__lt=timezone.localdate(),
        )
        .select_related("notice")
        .order_by("date_retour_prevue")
        .first()
    )


def suspension_active(emprunteur) -> SuspensionBibliotheque | None:
    aujourdhui = timezone.localdate()
    return (
        SuspensionBibliotheque.objects.filter(
            emprunteur=emprunteur,
            levee_le__isnull=True,
            date_debut__lte=aujourdhui,
            date_fin__gte=aujourdhui,
        )
        .select_related("emprunt", "emprunt__notice")
        .order_by("-date_fin")
        .first()
    )


def etat_emprunteur(emprunteur) -> dict:
    retard = emprunt_en_retard_actif(emprunteur)
    suspension = suspension_active(emprunteur)
    return {
        "bloque": bool(retard or suspension),
        "emprunt_retard": retard,
        "suspension": suspension,
    }


def verifier_droit_emprunt(emprunteur) -> None:
    retard = emprunt_en_retard_actif(emprunteur)
    if retard is not None:
        jours = (timezone.localdate() - retard.date_retour_prevue).days
        raise ValidationError(
            f"Nouveau prêt impossible : « {retard.notice.titre} » accuse {jours} jour(s) de retard. "
            "Restituez cet ouvrage avant toute nouvelle réservation."
        )

    suspension = suspension_active(emprunteur)
    if suspension is not None:
        raise ValidationError(
            "Nouveau prêt impossible : votre accès à la bibliothèque est suspendu "
            f"jusqu'au {suspension.date_fin.strftime('%d/%m/%Y')} inclus, à la suite d'un retard "
            f"de {suspension.jours_retard} jour(s)."
        )


@transaction.atomic
def reserver_ouvrage(
    notice: NoticeBibliographique,
    emprunteur,
    *,
    duree_jours: int = 21,
) -> Emprunt:
    """Réserve un ouvrage physique disponible pour retrait à l'institut."""
    verifier_droit_emprunt(emprunteur)
    notice = NoticeBibliographique.objects.select_for_update().get(pk=notice.pk)
    if not notice.disponible:
        raise ValidationError("Cet ouvrage est déjà emprunté ou indisponible.")

    if Emprunt.objects.filter(
        notice=notice,
        emprunteur=emprunteur,
        statut__in=[Emprunt.Statut.RESERVE, Emprunt.Statut.EN_COURS, Emprunt.Statut.EN_RETARD],
    ).exists():
        raise ValidationError("Vous avez déjà un emprunt ou une réservation en cours pour cet ouvrage.")

    date_retour = timezone.localdate() + timedelta(days=duree_jours)
    emprunt = Emprunt.objects.create(
        notice=notice,
        emprunteur=emprunteur,
        statut=Emprunt.Statut.RESERVE,
        date_retour_prevue=date_retour,
    )

    notice.disponible = False
    notice.save(update_fields=["disponible", "updated_at"])

    notifier(
        emprunteur,
        f"Ouvrage réservé — {notice.titre}",
        message=(
            f"Votre réservation de « {notice.titre} » est enregistrée. Présentez-vous au secrétariat pour le retrait. "
            f"Date de retour prévue : {date_retour.strftime('%d/%m/%Y')}."
        ),
        envoyer_par_email=True,
    )
    return emprunt


@transaction.atomic
def annuler_reservation(emprunt: Emprunt, emprunteur) -> NoticeBibliographique:
    """Annule une réservation d'ouvrage en cours et remet l'ouvrage disponible."""
    emprunt = Emprunt.objects.select_for_update().select_related("notice").get(pk=emprunt.pk)
    if emprunt.emprunteur_id != emprunteur.pk and not getattr(emprunteur, "is_staff", False):
        raise ValidationError("Vous n'êtes pas autorisé à annuler cette réservation.")
    if emprunt.statut != Emprunt.Statut.RESERVE:
        raise ValidationError("Seule une réservation en attente de retrait peut être annulée.")

    notice = emprunt.notice
    notice.disponible = True
    notice.save(update_fields=["disponible", "updated_at"])
    emprunt.delete()

    notifier(
        emprunteur,
        f"Réservation annulée — {notice.titre}",
        message=f"Votre réservation pour « {notice.titre} » a été annulée avec succès.",
        envoyer_par_email=True,
    )
    return notice


@transaction.atomic
def valider_retrait(emprunt: Emprunt) -> Emprunt:
    """Valide le retrait effectif après un dernier contrôle d'éligibilité."""
    emprunt = Emprunt.objects.select_for_update().select_related("emprunteur").get(pk=emprunt.pk)
    if emprunt.statut != Emprunt.Statut.RESERVE:
        raise ValidationError("Seul un ouvrage réservé peut être marqué comme retiré.")

    verifier_droit_emprunt(emprunt.emprunteur)
    emprunt.statut = Emprunt.Statut.EN_COURS
    emprunt.date_retrait = timezone.now()
    emprunt.save(update_fields=["statut", "date_retrait", "updated_at"])
    return emprunt


@transaction.atomic
def restituer_ouvrage(emprunt: Emprunt, *, commentaire: str = "") -> Emprunt:
    """Enregistre le retour, remet l'ouvrage en rayon et sanctionne le retard."""
    emprunt = (
        Emprunt.objects.select_for_update()
        .select_related("notice", "emprunteur")
        .get(pk=emprunt.pk)
    )
    if emprunt.statut == Emprunt.Statut.RENDU:
        return emprunt

    date_retour = timezone.localdate()
    jours_retard = max(0, (date_retour - emprunt.date_retour_prevue).days)

    emprunt.statut = Emprunt.Statut.RENDU
    emprunt.date_retour_effectif = date_retour
    if commentaire:
        emprunt.commentaire = commentaire.strip()
    emprunt.save(update_fields=["statut", "date_retour_effectif", "commentaire", "updated_at"])

    notice = emprunt.notice
    notice.disponible = True
    notice.save(update_fields=["disponible", "updated_at"])

    if jours_retard > 0:
        jours_suspension = _duree_suspension(jours_retard)
        date_fin = date_retour + timedelta(days=jours_suspension - 1)
        suspension, _ = SuspensionBibliotheque.objects.update_or_create(
            emprunt=emprunt,
            defaults={
                "emprunteur": emprunt.emprunteur,
                "jours_retard": jours_retard,
                "jours_suspension": jours_suspension,
                "date_debut": date_retour,
                "date_fin": date_fin,
                "levee_le": None,
                "levee_par": None,
                "motif_levee": "",
            },
        )
        notifier(
            emprunt.emprunteur,
            f"Suspension de prêt — {notice.titre}",
            message=(
                f"L'ouvrage « {notice.titre} » a été restitué avec {jours_retard} jour(s) de retard. "
                "Conformément à la règle de prêt, toute nouvelle réservation est suspendue jusqu'au "
                f"{suspension.date_fin.strftime('%d/%m/%Y')} inclus."
            ),
            envoyer_par_email=True,
        )
    return emprunt


@transaction.atomic
def lever_suspension(suspension: SuspensionBibliotheque, *, par, motif: str) -> SuspensionBibliotheque:
    """Levée exceptionnelle, nécessairement motivée et tracée."""
    suspension = SuspensionBibliotheque.objects.select_for_update().get(pk=suspension.pk)
    if suspension.levee_le is not None:
        return suspension

    motif = (motif or "").strip()
    if not motif:
        raise ValidationError("Le motif de la levée de suspension est obligatoire.")

    suspension.levee_le = timezone.now()
    suspension.levee_par = par
    suspension.motif_levee = motif
    suspension.save(update_fields=["levee_le", "levee_par", "motif_levee", "updated_at"])

    notifier(
        suspension.emprunteur,
        "Suspension de bibliothèque levée",
        message=(
            "Le secrétariat a levé votre suspension de prêt. Vous pouvez de nouveau réserver un ouvrage. "
            f"Motif : {motif}"
        ),
        envoyer_par_email=True,
    )
    return suspension


@transaction.atomic
def verifier_retards() -> int:
    """Passe en retard les prêts échus et informe de la règle de sanction."""
    aujourdhui = timezone.localdate()
    emprunts_retard = Emprunt.objects.filter(
        statut=Emprunt.Statut.EN_COURS,
        date_retour_prevue__lt=aujourdhui,
    ).select_related("notice", "emprunteur")
    count = 0
    for emprunt in emprunts_retard:
        emprunt.statut = Emprunt.Statut.EN_RETARD
        emprunt.save(update_fields=["statut", "updated_at"])
        count += 1
        dt_fmt = emprunt.date_retour_prevue.strftime("%d/%m/%Y")
        notifier(
            emprunt.emprunteur,
            f"Retard de restitution — {emprunt.notice.titre}",
            message=(
                f"La date de retour de « {emprunt.notice.titre} » était le {dt_fmt}. "
                "Tout nouveau prêt est bloqué jusqu'à la restitution. Une suspension d'un jour par jour "
                "de retard sera ensuite appliquée, dans la limite de 30 jours."
            ),
            envoyer_par_email=True,
        )
    return count


@transaction.atomic
def envoyer_rappels_echeances_proches(jours_avant: int = 3) -> int:
    """Envoie un rappel par email pour les emprunts dont l'échéance approche."""
    date_cible = timezone.localdate() + timedelta(days=jours_avant)
    emprunts_proches = Emprunt.objects.filter(
        statut__in=[Emprunt.Statut.EN_COURS, Emprunt.Statut.RESERVE],
        date_retour_prevue=date_cible,
    ).select_related("notice", "emprunteur")

    count = 0
    for emprunt in emprunts_proches:
        dt_fmt = emprunt.date_retour_prevue.strftime("%d/%m/%Y")
        notifier(
            emprunt.emprunteur,
            f"Rappel : échéance proche pour « {emprunt.notice.titre} »",
            message=(
                f"La date de restitution de l'ouvrage « {emprunt.notice.titre} » approche (échéance le {dt_fmt}). "
                "Après l'échéance, tout nouveau prêt sera bloqué et le retard entraînera une suspension."
            ),
            envoyer_par_email=True,
        )
        count += 1
    return count
