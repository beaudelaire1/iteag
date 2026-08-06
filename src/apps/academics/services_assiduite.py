from django.core.exceptions import ValidationError
from django.db import transaction

from apps.academics.models import InscriptionSession
from apps.academics.models_assiduite import HistoriquePresence, Presence


@transaction.atomic
def enregistrer_presence(*, seance, etudiant, statut, commentaire, auteur):
    """Crée ou corrige une présence en conservant la valeur précédente."""

    statuts_valides = {valeur for valeur, _ in Presence.Statut.choices}
    if statut not in statuts_valides:
        raise ValidationError("Statut de présence invalide.")
    if not InscriptionSession.objects.filter(
        cours_session=seance.cours_session,
        etudiant=etudiant,
    ).exists():
        raise ValidationError("Cet étudiant n'est pas inscrit à ce cours.")

    commentaire = (commentaire or "").strip()
    presence, creee = Presence.objects.select_for_update().get_or_create(
        seance=seance,
        etudiant=etudiant,
        defaults={
            "statut": statut,
            "commentaire": commentaire,
            "saisi_par": auteur,
            "modifie_par": auteur,
        },
    )
    if creee:
        return presence

    if presence.statut == statut and presence.commentaire == commentaire:
        return presence

    HistoriquePresence.objects.create(
        presence=presence,
        ancien_statut=presence.statut,
        nouveau_statut=statut,
        ancien_commentaire=presence.commentaire,
        nouveau_commentaire=commentaire,
        modifie_par=auteur,
    )
    presence.statut = statut
    presence.commentaire = commentaire
    presence.modifie_par = auteur
    presence.save(update_fields=["statut", "commentaire", "modifie_par", "updated_at"])
    return presence
