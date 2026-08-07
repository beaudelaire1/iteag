"""Workflow transactionnel des demandes d'inscription aux cours."""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from apps.academics.models import (
    DemandeInscriptionCours,
    HistoriqueDemandeInscription,
    InscriptionSession,
    Paiement,
    ProfilEtudiant,
)
from apps.accounts.models import User
from apps.core.models import JournalAudit, Notification
from apps.core.services.audit import journaliser
from apps.core.services.notifications import notifier, notifier_plusieurs

STATUTS_ETUDIANT_AUTORISES = {
    ProfilEtudiant.StatutInscription.PRE_INSCRIT,
    ProfilEtudiant.StatutInscription.PAIEMENT_ATTENTE,
    ProfilEtudiant.StatutInscription.INSCRIT,
    ProfilEtudiant.StatutInscription.ACTIF,
}


def verifier_eligibilite(etudiant, cours_session):
    """Retourne le motif de blocage, ou une chaîne vide si la demande est recevable."""
    if etudiant.statut_inscription not in STATUTS_ETUDIANT_AUTORISES:
        return "Votre statut administratif ne permet pas une nouvelle inscription."
    if InscriptionSession.objects.filter(etudiant=etudiant, cours_session=cours_session).exists():
        return "Vous êtes déjà inscrit à ce cours."
    return cours_session.motif_indisponibilite(etudiant)


@transaction.atomic
def soumettre_demande(
    *,
    etudiant,
    cours_session,
    note_etudiant="",
    reference_paiement="",
    justificatif_paiement=None,
    request=None,
):
    """Crée ou resoumet une demande terminale après tous les contrôles métier."""
    cours_session = (
        type(cours_session)
        .objects.select_for_update()
        .select_related("cours", "session", "enseignant")
        .get(pk=cours_session.pk)
    )
    motif = verifier_eligibilite(etudiant, cours_session)
    if motif:
        raise ValidationError(motif)

    demande, creee = DemandeInscriptionCours.objects.select_for_update().get_or_create(
        etudiant=etudiant,
        cours_session=cours_session,
        defaults={
            "montant_du": cours_session.montant_pour(etudiant),
            "note_etudiant": note_etudiant,
            "reference_paiement": reference_paiement,
            "justificatif_paiement": justificatif_paiement,
        },
    )
    if not creee:
        if demande.statut not in {
            DemandeInscriptionCours.Statut.REFUSEE,
            DemandeInscriptionCours.Statut.ANNULEE,
        }:
            raise ValidationError("Une demande est déjà en cours pour ce cours.")
        ancien_statut = demande.statut
        demande.statut = DemandeInscriptionCours.Statut.SOUMISE
        demande.montant_du = cours_session.montant_pour(etudiant)
        demande.note_etudiant = note_etudiant
        demande.reference_paiement = reference_paiement
        demande.justificatif_paiement = justificatif_paiement
        demande.paiement = None
        demande.exonere_paiement = False
        demande.traitee_par = None
        demande.date_decision = None
        demande.motif_decision = ""
        demande.save()
    else:
        ancien_statut = ""

    HistoriqueDemandeInscription.objects.create(
        demande=demande,
        ancien_statut=ancien_statut,
        nouveau_statut=demande.statut,
        modifie_par=etudiant.utilisateur,
        commentaire="Demande soumise par l'étudiant.",
    )
    journaliser(
        JournalAudit.Action.CREATION,
        utilisateur=etudiant.utilisateur,
        request=request,
        objet=demande,
        montant=str(demande.montant_du),
    )
    notifier(
        etudiant.utilisateur,
        f"Demande d'inscription enregistrée — {cours_session.cours.titre}",
        type_notification=Notification.Type.RAPPEL_SESSION,
        message=(
            f"Votre demande d'inscription au cours « {cours_session.cours.titre} » a bien été reçue. "
            "Le secrétariat va l'examiner ; vous serez averti dès qu'une décision sera prise. "
            "Aucune démarche n'est à faire de votre part dans l'intervalle."
        ),
        details=_details_demande(demande),
        url_cible=reverse("etudiant:enrollment_requests"),
    )
    notifier_plusieurs(
        User.objects.filter(
            is_active=True,
            role__in=[User.Role.ADMIN, User.Role.SECRETARIAT],
        ),
        f"Nouvelle demande d'inscription — {cours_session.cours.titre}",
        type_notification=Notification.Type.RAPPEL_SESSION,
        message=(
            f"{etudiant} demande à suivre le cours « {cours_session.cours.titre} ». "
            "La demande attend une décision dans l'espace administratif."
        ),
        details=[{"libelle": "Étudiant", "valeur": str(etudiant)}, *_details_demande(demande)],
        url_cible=reverse("administration:enrollment_request_detail", kwargs={"pk": demande.pk}),
    )
    return demande


@transaction.atomic
def annuler_demande(*, demande, etudiant, request=None):
    demande = DemandeInscriptionCours.objects.select_for_update().get(pk=demande.pk, etudiant=etudiant)
    if not demande.peut_etre_annulee:
        raise ValidationError("Cette demande ne peut plus être annulée.")
    _changer_statut(
        demande,
        DemandeInscriptionCours.Statut.ANNULEE,
        acteur=etudiant.utilisateur,
        commentaire="Annulation demandée par l'étudiant.",
    )
    journaliser(
        JournalAudit.Action.CHANGEMENT_STATUT,
        utilisateur=etudiant.utilisateur,
        request=request,
        objet=demande,
        nouveau_statut=demande.statut,
    )
    notifier(
        etudiant.utilisateur,
        f"Demande d'inscription annulée — {demande.cours_session.cours.titre}",
        type_notification=Notification.Type.RAPPEL_SESSION,
        message=(
            f"Votre demande d'inscription au cours « {demande.cours_session.cours.titre} » a été "
            "annulée à votre initiative. Ce message en vaut confirmation. Vous pouvez déposer une "
            "nouvelle demande tant que les inscriptions restent ouvertes."
        ),
        details=_details_demande(demande),
        url_cible=reverse("etudiant:enrollment_requests"),
    )
    return demande


@transaction.atomic
def traiter_demande(
    *,
    demande,
    action,
    par,
    commentaire="",
    paiement=None,
    exonere_paiement=False,
    request=None,
):
    """Applique une transition staff et crée l'inscription lors de la confirmation."""
    # Le verrou ne porte que sur la demande elle-même. « formule_tarif » est
    # facultatif : sa jointure est externe, et PostgreSQL refuse un FOR UPDATE
    # sur le côté nullable d'une jointure externe. SQLite l'acceptait
    # silencieusement — d'où un échec visible seulement en intégration.
    # Verrouiller les lignes jointes n'était de toute façon pas l'intention :
    # c'est la demande qu'on protège d'un traitement concurrent.
    demande = (
        DemandeInscriptionCours.objects.select_for_update(of=("self",))
        .select_related(
            "etudiant__utilisateur",
            "etudiant__formule_tarif",
            "cours_session__cours",
            "cours_session__session",
        )
        .get(pk=demande.pk)
    )
    transitions = {
        "demander_paiement": (
            {DemandeInscriptionCours.Statut.SOUMISE},
            DemandeInscriptionCours.Statut.PAIEMENT_ATTENTE,
        ),
        "confirmer": (
            {
                DemandeInscriptionCours.Statut.SOUMISE,
                DemandeInscriptionCours.Statut.PAIEMENT_ATTENTE,
            },
            DemandeInscriptionCours.Statut.CONFIRMEE,
        ),
        "refuser": (
            {
                DemandeInscriptionCours.Statut.SOUMISE,
                DemandeInscriptionCours.Statut.PAIEMENT_ATTENTE,
            },
            DemandeInscriptionCours.Statut.REFUSEE,
        ),
        "reouvrir": (
            {
                DemandeInscriptionCours.Statut.REFUSEE,
                DemandeInscriptionCours.Statut.ANNULEE,
            },
            DemandeInscriptionCours.Statut.SOUMISE,
        ),
    }
    if action not in transitions:
        raise ValidationError("Action inconnue.")
    sources, cible = transitions[action]

    # Un double clic, un retour arrière ou une reprise réseau peut rejouer
    # exactement la décision qui vient d'aboutir. L'opération est alors
    # idempotente : elle ne crée ni second historique, ni message d'erreur.
    if demande.statut == cible:
        return demande

    if demande.statut not in sources:
        raise ValidationError(
            "Cette demande a déjà changé d'état. Rechargez la page avant d'appliquer une nouvelle décision."
        )
    if action == "refuser" and not commentaire.strip():
        raise ValidationError("Précisez le motif du refus.")

    if action == "demander_paiement" and demande.montant_du <= 0:
        raise ValidationError("Aucun paiement n'est requis : confirmez directement l'inscription.")

    if action == "confirmer":
        _confirmer_inscription(
            demande,
            par=par,
            paiement=paiement,
            exonere_paiement=exonere_paiement,
            commentaire=commentaire,
        )
    else:
        _changer_statut(demande, cible, acteur=par, commentaire=commentaire)
        if action == "reouvrir":
            demande.paiement = None
            demande.exonere_paiement = False
            demande.save(update_fields=["paiement", "exonere_paiement", "updated_at"])

    journaliser(
        JournalAudit.Action.CHANGEMENT_STATUT,
        utilisateur=par,
        request=request,
        objet=demande,
        nouveau_statut=demande.statut,
        action_metier=action,
    )
    notifier(
        demande.etudiant.utilisateur,
        f"{_titre_notification(demande.statut)} — {demande.cours_session.cours.titre}",
        type_notification=Notification.Type.RAPPEL_SESSION,
        message=_message_notification(demande),
        details=_details_demande(demande),
        url_cible=reverse("etudiant:enrollment_requests"),
    )
    return demande


def _confirmer_inscription(demande, *, par, paiement, exonere_paiement, commentaire):
    cours_session = type(demande.cours_session).objects.select_for_update().get(pk=demande.cours_session_id)
    deja_inscrit = InscriptionSession.objects.filter(
        etudiant=demande.etudiant,
        cours_session=cours_session,
    ).first()

    # La recevabilité publique a été vérifiée au dépôt de la demande.
    # Le secrétariat ne rejoue donc pas la fermeture des inscriptions,
    # la date limite, le statut du cours ou le parcours au moment de statuer.
    # Ces valeurs peuvent légitimement évoluer pendant l'instruction.
    if deja_inscrit:
        raise ValidationError("Cet étudiant est déjà inscrit à ce cours.")
    if cours_session.places_restantes <= 0:
        raise ValidationError("Ce cours est complet : aucune place ne peut être attribuée.")

    paiement_valide = paiement or _paiement_confirme_compatible(demande)
    if demande.montant_du > 0 and not exonere_paiement:
        if paiement_valide is None:
            raise ValidationError("Un paiement confirmé couvrant cette session est requis.")
        if paiement_valide.montant < demande.montant_du:
            raise ValidationError("Le paiement confirmé ne couvre pas le montant dû.")
    if exonere_paiement and not commentaire.strip():
        raise ValidationError("Justifiez l'exonération dans le commentaire interne.")

    ancien_statut = demande.statut
    demande.statut = DemandeInscriptionCours.Statut.CONFIRMEE
    demande.paiement = paiement_valide
    demande.exonere_paiement = exonere_paiement
    demande.traitee_par = par
    demande.date_decision = timezone.now()
    demande.motif_decision = commentaire
    demande.save()
    InscriptionSession.objects.get_or_create(
        etudiant=demande.etudiant,
        cours_session=cours_session,
        defaults={"demande": demande},
    )
    if demande.etudiant.statut_inscription in {
        ProfilEtudiant.StatutInscription.PRE_INSCRIT,
        ProfilEtudiant.StatutInscription.PAIEMENT_ATTENTE,
    }:
        demande.etudiant.statut_inscription = ProfilEtudiant.StatutInscription.INSCRIT
        demande.etudiant.save(update_fields=["statut_inscription", "updated_at"])
    HistoriqueDemandeInscription.objects.create(
        demande=demande,
        ancien_statut=ancien_statut,
        nouveau_statut=demande.statut,
        modifie_par=par,
        commentaire=commentaire,
    )


def _paiement_confirme_compatible(demande):
    return (
        Paiement.objects.filter(
            etudiant=demande.etudiant,
            session=demande.cours_session.session,
            statut=Paiement.StatutPaiement.CONFIRME,
        )
        .order_by("-date_paiement", "-created_at")
        .first()
    )


def _changer_statut(demande, statut, *, acteur, commentaire):
    ancien_statut = demande.statut
    demande.statut = statut
    demande.traitee_par = acteur
    demande.date_decision = timezone.now()
    demande.motif_decision = commentaire
    demande.save(update_fields=["statut", "traitee_par", "date_decision", "motif_decision", "updated_at"])
    HistoriqueDemandeInscription.objects.create(
        demande=demande,
        ancien_statut=ancien_statut,
        nouveau_statut=statut,
        modifie_par=acteur,
        commentaire=commentaire,
    )


def _details_demande(demande) -> list[dict]:
    """Cours, session, état et éventuel motif : le courriel doit être autonome."""
    cours_session = demande.cours_session
    details = [
        {"libelle": "Cours", "valeur": cours_session.cours.titre},
        {"libelle": "Session", "valeur": str(cours_session.session)},
        {"libelle": "État de la demande", "valeur": demande.get_statut_display()},
    ]
    if demande.montant_du:
        details.append({"libelle": "Montant dû", "valeur": f"{demande.montant_du} €"})
    motif = (demande.motif_decision or "").strip()
    if demande.statut == DemandeInscriptionCours.Statut.REFUSEE and motif:
        details.append({"libelle": "Motif du refus", "valeur": motif})
    return details


def _message_notification(demande) -> str:
    """Ce que l'étudiant doit comprendre — et faire — selon l'état de sa demande.

    Un avis qui se contente de nommer un statut laisse son destinataire deviner
    ce qu'on attend de lui. Le motif saisi par le secrétariat doit donc apparaître
    directement dans le message de refus, sans obliger l'étudiant à se connecter.
    """
    cours = demande.cours_session.cours.titre
    motif = (demande.motif_decision or "").strip()
    message_refus = (
        f"Votre demande d'inscription au cours « {cours} » n'a pas été retenue. "
        f"Motif communiqué par le secrétariat : {motif}"
        if motif
        else (
            f"Votre demande d'inscription au cours « {cours} » n'a pas été retenue. "
            "Contactez le secrétariat pour obtenir les précisions utiles."
        )
    )
    return {
        DemandeInscriptionCours.Statut.PAIEMENT_ATTENTE: (
            f"Votre inscription au cours « {cours} » est acceptée sous réserve de règlement. "
            "Elle sera définitive dès réception du paiement, dont le montant figure ci-dessous. "
            "Le secrétariat se tient à votre disposition pour en convenir des modalités."
        ),
        DemandeInscriptionCours.Statut.CONFIRMEE: (
            f"Votre inscription au cours « {cours} » est confirmée. Le cours apparaît désormais "
            "dans votre espace étudiant, avec ses ressources et ses évaluations."
        ),
        DemandeInscriptionCours.Statut.REFUSEE: message_refus,
        DemandeInscriptionCours.Statut.SOUMISE: (
            f"Votre demande d'inscription au cours « {cours} » a été rouverte et va être réexaminée par le secrétariat."
        ),
    }.get(
        demande.statut,
        f"L'état de votre demande d'inscription au cours « {cours} » a changé : "
        f"{demande.get_statut_display().lower()}.",
    )


def _titre_notification(statut):
    return {
        # Le cours est ajouté au titre par l'appelant : ces libellés restent
        # courts pour que l'objet du courriel tienne dans une ligne de boîte
        # de réception, où il est tronqué au-delà d'une soixantaine de signes.
        DemandeInscriptionCours.Statut.PAIEMENT_ATTENTE: "Paiement requis",
        DemandeInscriptionCours.Statut.CONFIRMEE: "Inscription confirmée",
        DemandeInscriptionCours.Statut.REFUSEE: "Demande d'inscription non retenue",
        DemandeInscriptionCours.Statut.SOUMISE: "Demande d'inscription rouverte",
    }.get(statut, "Mise à jour de votre demande d'inscription")
