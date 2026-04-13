"""Service d'envoi d'emails pour les admissions — CDC §7.1."""

from django.conf import settings
from django.core.mail import send_mail
from django.urls import reverse


def send_candidature_confirmation(dossier):
    """Email de confirmation envoyé au candidat après soumission (PUB-011)."""
    suivi_url = f"{settings.SITE_URL}{reverse('admissions:candidature_suivi', kwargs={'token': dossier.token_suivi})}"

    send_mail(
        subject="ITEAG — Votre candidature a bien été enregistrée",
        message=(
            f"Bonjour {dossier.prenom},\n\n"
            f"Nous avons bien reçu votre candidature pour le parcours "
            f"« {dossier.parcours_souhaite} ».\n\n"
            f"Votre dossier est en cours d'examen. Vous pouvez suivre son avancement "
            f"à tout moment via ce lien :\n{suivi_url}\n\n"
            f"Nous reviendrons vers vous dans les meilleurs délais.\n\n"
            f"Cordialement,\n"
            f"Le secrétariat de l'ITEAG"
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[dossier.email],
        fail_silently=True,
    )


def send_statut_change_email(dossier):
    """Email envoyé au candidat lors d'un changement de statut (ADM-001)."""
    from .models import DossierCandidature

    suivi_url = f"{settings.SITE_URL}{reverse('admissions:candidature_suivi', kwargs={'token': dossier.token_suivi})}"

    subject_map = {
        DossierCandidature.Statut.EN_EXAMEN: None,  # Pas d'email à cette étape (CDC §7.1)
        DossierCandidature.Statut.INCOMPLET: "ITEAG — Votre dossier est incomplet",
        DossierCandidature.Statut.ACCEPTE: "ITEAG — Votre candidature est acceptée",
        DossierCandidature.Statut.REFUSE: "ITEAG — Réponse à votre candidature",
    }

    body_map = {
        DossierCandidature.Statut.INCOMPLET: (
            f"Bonjour {dossier.prenom},\n\n"
            f"Après examen de votre dossier, il apparaît que certains éléments "
            f"sont manquants ou à compléter :\n\n"
            f"{dossier.elements_manquants or 'Veuillez nous contacter pour plus de détails.'}\n\n"
            f"Vous pouvez suivre l'état de votre dossier ici :\n{suivi_url}\n\n"
            f"Cordialement,\nLe secrétariat de l'ITEAG"
        ),
        DossierCandidature.Statut.ACCEPTE: (
            f"Bonjour {dossier.prenom},\n\n"
            f"Nous avons le plaisir de vous informer que votre candidature "
            f"pour le parcours « {dossier.parcours_souhaite} » a été acceptée.\n\n"
            f"Vous recevrez prochainement les instructions pour finaliser "
            f"votre inscription et procéder au règlement.\n\n"
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
        return  # Pas d'email pour EN_EXAMEN ni SOUMIS

    body = body_map.get(dossier.statut, "")

    send_mail(
        subject=subject,
        message=body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[dossier.email],
        fail_silently=True,
    )
