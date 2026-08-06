"""Workflows transactionnels pour les emprunts de la bibliothèque."""

from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.core.services.notifications import notifier
from apps.library.models import Emprunt, NoticeBibliographique


@transaction.atomic
def reserver_ouvrage(
    notice: NoticeBibliographique,
    emprunteur,
    *,
    duree_jours: int = 21,
) -> Emprunt:
    """Réserve un ouvrage physique disponible pour retrait à l'institut."""
    notice = NoticeBibliographique.objects.select_for_update().get(pk=notice.pk)
    if not notice.disponible:
        raise ValidationError("Cet ouvrage est déjà emprunté ou indisponible.")

    # Vérifier si l'utilisateur a déjà une réservation/emprunt en cours pour cette notice
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
            f"Votre réservation de « {notice.titre} » est enregistrée. Présentez-vous au secrétariat pour le retrait."
        ),
        envoyer_par_email=False,
    )

    return emprunt


@transaction.atomic
def valider_retrait(emprunt: Emprunt) -> Emprunt:
    """Valide le retrait effectif de l'ouvrage par l'emprunteur."""
    emprunt = Emprunt.objects.select_for_update().get(pk=emprunt.pk)
    if emprunt.statut != Emprunt.Statut.RESERVE:
        raise ValidationError("Seul un ouvrage réservé peut être marqué comme retiré.")

    emprunt.statut = Emprunt.Statut.EN_COURS
    emprunt.date_retrait = timezone.now()
    emprunt.save(update_fields=["statut", "date_retrait", "updated_at"])

    return emprunt


@transaction.atomic
def restituer_ouvrage(emprunt: Emprunt, *, commentaire: str = "") -> Emprunt:
    """Enregistre le retour de l'ouvrage physique et le remet en disponibilité."""
    emprunt = Emprunt.objects.select_for_update().select_related("notice").get(pk=emprunt.pk)
    if emprunt.statut == Emprunt.Statut.RENDU:
        return emprunt

    emprunt.statut = Emprunt.Statut.RENDU
    emprunt.date_retour_effectif = timezone.localdate()
    if commentaire:
        emprunt.commentaire = commentaire.strip()
    emprunt.save(update_fields=["statut", "date_retour_effectif", "commentaire", "updated_at"])

    notice = emprunt.notice
    notice.disponible = True
    notice.save(update_fields=["disponible", "updated_at"])

    return emprunt


@transaction.atomic
def verifier_retards() -> int:
    """Passe en statut 'en_retard' les emprunts dont la date de retour prévue est dépassée."""
    aujourdhui = timezone.localdate()
    emprunts_retard = Emprunt.objects.filter(
        statut=Emprunt.Statut.EN_COURS,
        date_retour_prevue__lt=aujourdhui,
    )
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
                "Merci de le restituer au secrétariat dès que possible."
            ),
            envoyer_par_email=True,
        )
    return count
