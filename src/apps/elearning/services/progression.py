"""
Suivi de progression — calculé et validé côté serveur.

Le client annonce sa position et le temps écoulé depuis le dernier signal.
Le serveur plafonne cet incrément : c'est ce qui empêche de simuler un
visionnage complet pour obtenir une attestation.
"""

import logging

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.elearning.models import AttestationModule, InscriptionModule, Lecon, ProgressionLecon

logger = logging.getLogger(__name__)

# Un signal est émis toutes les 15 s ; on tolère le double pour absorber une
# latence réseau, jamais davantage.
INCREMENT_MAX_SECONDES = 30


def enregistrer_progression(
    inscription: InscriptionModule,
    lecon: Lecon,
    *,
    position_secondes: int,
    delta_secondes: int,
) -> ProgressionLecon:
    """Met à jour l'avancement sur une leçon et, si besoin, sur le module."""
    duree = max(lecon.duree_secondes, 0)
    position = max(0, min(int(position_secondes), duree or int(position_secondes)))
    delta = max(0, min(int(delta_secondes), INCREMENT_MAX_SECONDES))

    with transaction.atomic():
        progression, _ = ProgressionLecon.objects.select_for_update().get_or_create(
            inscription=inscription,
            lecon=lecon,
        )

        progression.position_secondes = position
        # Le cumul ne peut pas dépasser la durée réelle : au-delà, c'est du replay.
        plafond = duree if duree else progression.temps_visionnage_cumule + delta
        progression.temps_visionnage_cumule = min(progression.temps_visionnage_cumule + delta, plafond)
        progression.pourcentage_vu = _pourcentage(progression.temps_visionnage_cumule, duree, position)
        progression.date_derniere_vue = timezone.now()

        seuil = inscription.module.seuil_completion
        if not progression.termine and _lecon_achevee(progression, duree, seuil):
            progression.termine = True
            progression.date_completion = timezone.now()

        progression.save()

    recalculer_progression_module(inscription)
    return progression


def _pourcentage(temps_vu: int, duree: int, position: int) -> int:
    if duree <= 0:
        return 100 if position > 0 else 0
    return min(100, round(temps_vu / duree * 100))


def _lecon_achevee(progression: ProgressionLecon, duree: int, seuil: int) -> bool:
    """Une leçon n'est achevée que si elle a réellement été visionnée.

    Le pourcentage seul ne suffirait pas : il se falsifie en déplaçant le
    curseur. Le temps cumulé, lui, est plafonné à chaque signal.
    """
    if duree <= 0:
        return progression.position_secondes > 0
    return progression.temps_visionnage_cumule >= duree * seuil / 100


def recalculer_progression_module(inscription: InscriptionModule) -> int:
    """Recalcule le pourcentage du module et clôt l'accès si le seuil est atteint."""
    lecons_obligatoires = list(inscription.module.lecons().filter(obligatoire=True).values_list("pk", flat=True))
    if not lecons_obligatoires:
        return inscription.progression_percent

    terminees = ProgressionLecon.objects.filter(
        inscription=inscription,
        lecon_id__in=lecons_obligatoires,
        termine=True,
    ).count()
    pourcentage = round(terminees / len(lecons_obligatoires) * 100)

    champs = []
    if pourcentage != inscription.progression_percent:
        inscription.progression_percent = pourcentage
        champs.append("progression_percent")

    atteint = pourcentage >= inscription.module.seuil_completion
    if atteint and inscription.statut == InscriptionModule.StatutAcces.ACTIF:
        inscription.statut = InscriptionModule.StatutAcces.TERMINE
        inscription.date_completion = timezone.now()
        champs += ["statut", "date_completion"]

    if champs:
        inscription.save(update_fields=[*champs, "updated_at"])

    if atteint and inscription.module.certifiant:
        emettre_attestation(inscription)

    return pourcentage


def emettre_attestation(inscription: InscriptionModule) -> AttestationModule | None:
    """Crée l'attestation si le module est certifiant et le seuil atteint."""
    if not inscription.module.certifiant:
        return None
    if inscription.progression_percent < inscription.module.seuil_completion:
        return None

    attestation, creee = AttestationModule.objects.get_or_create(inscription=inscription)
    if creee:
        from apps.core.models import Notification
        from apps.core.services.notifications import notifier

        notifier(
            inscription.etudiant.utilisateur,
            f"Attestation disponible — {inscription.module.titre}",
            type_notification=Notification.Type.ATTESTATION,
            message=(
                f"Vous avez terminé le module « {inscription.module.titre} » : félicitations. "
                "Votre attestation de suivi est établie à votre nom et téléchargeable depuis votre "
                "espace. Elle porte un code de vérification qui permet à un tiers d'en contrôler "
                "l'authenticité en ligne."
            ),
            details=[
                {"libelle": "Module", "valeur": inscription.module.titre},
                {"libelle": "Progression", "valeur": f"{inscription.progression_percent} %"},
                {"libelle": "N° d'attestation", "valeur": attestation.numero},
            ],
            url_cible=inscription.module.get_absolute_url(),
        )
        if getattr(settings, "ELEARNING_ATTESTATION_PDF", True):
            from apps.elearning.tasks import generer_attestation_pdf

            try:
                generer_attestation_pdf.delay(str(attestation.pk))
            except Exception:  # noqa: BLE001 — l'attestation existe déjà, le PDF suivra
                logger.warning(
                    "Génération du PDF de l'attestation %s différée : courtier indisponible",
                    attestation.numero,
                    exc_info=True,
                )
    return attestation


def lecon_suivante(inscription: InscriptionModule) -> Lecon | None:
    """Première leçon non terminée, pour la reprise du parcours."""
    deja_faites = set(
        ProgressionLecon.objects.filter(inscription=inscription, termine=True).values_list("lecon_id", flat=True)
    )
    for lecon in inscription.module.lecons():
        if lecon.pk not in deja_faites:
            return lecon
    return None
