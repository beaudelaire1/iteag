from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.accounts.models import User
from apps.core.models import Notification
from apps.core.services.emails import envoyer_notification_email
from apps.core.services.notifications import notifier_plusieurs
from apps.core.services.turnstile import MESSAGE_ECHEC, valider_requete
from apps.formations.models import Parcours

from .emails import send_candidature_confirmation
from .forms import CandidatureForm
from .formulaires import DepotPieceForm
from .models import DossierCandidature


def candidature_form(request):
    """Vue publique : formulaire de candidature (PUB-011)."""
    if request.method == "POST":
        form = CandidatureForm(request.POST, request.FILES)
        if form.is_valid():
            if valider_requete(request, action="candidature"):
                dossier = form.save()
                send_candidature_confirmation(dossier)
                notifier_plusieurs(
                    User.objects.filter(
                        is_active=True,
                        role__in=[User.Role.ADMIN, User.Role.SECRETARIAT],
                    ),
                    f"Nouvelle candidature — {dossier.nom_complet}",
                    type_notification=Notification.Type.CANDIDATURE,
                    message=(
                        f"{dossier.nom_complet} a déposé une candidature pour le parcours "
                        f"« {dossier.parcours_souhaite} ». Le dossier attend un premier examen."
                    ),
                    details=[
                        {"libelle": "Candidat", "valeur": dossier.nom_complet},
                        {"libelle": "Parcours demandé", "valeur": str(dossier.parcours_souhaite)},
                        {"libelle": "Courriel", "valeur": dossier.email},
                    ],
                    url_cible=reverse("administration:candidature_detail", kwargs={"pk": dossier.pk}),
                )
                messages.success(request, "Votre candidature a bien été enregistrée.")
                return redirect("admissions:candidature_confirmation", token=dossier.token_suivi)
            form.add_error(None, MESSAGE_ECHEC)
    else:
        form = CandidatureForm()
    return render(request, "admissions/candidature_form.html", {"form": form})


def candidature_confirmation(request, token):
    """Page de confirmation après soumission."""
    dossier = get_object_or_404(DossierCandidature, token_suivi=token)
    return render(request, "admissions/candidature_confirmation.html", {"dossier": dossier})


def candidature_suivi(request, token):
    """Suivi public du dossier via lien signé."""
    dossier = get_object_or_404(DossierCandidature, token_suivi=token)
    pieces = dossier.pieces_demandees.all()
    return render(
        request,
        "admissions/candidature_suivi.html",
        {
            "dossier": dossier,
            "pieces": pieces,
            "pieces_a_fournir": [p for p in pieces if not p.est_fournie],
            "formulaire_depot": DepotPieceForm(),
        },
    )


@require_POST
def deposer_piece(request, token, piece_id):
    """Dépôt d'une pièce par le candidat, depuis sa page de suivi.

    Le jeton de suivi tient lieu d'authentification : le candidat n'a pas de
    compte, et lui en imposer un pour transmettre un acte de naissance ferait
    abandonner la moitié des dossiers. Le jeton est long, non devinable, et ne
    donne accès qu'à ce dossier — la pièce est d'ailleurs relue depuis le
    dossier lui-même, jamais depuis son seul identifiant.
    """
    dossier = get_object_or_404(DossierCandidature, token_suivi=token)
    piece = get_object_or_404(dossier.pieces_demandees, pk=piece_id)

    formulaire = DepotPieceForm(request.POST, request.FILES, instance=piece)
    if formulaire.is_valid():
        piece.deposer(formulaire.cleaned_data["fichier"])
        suivi_url = request.build_absolute_uri(
            reverse("admissions:candidature_suivi", kwargs={"token": dossier.token_suivi})
        )
        envoyer_notification_email(
            sujet=f"Document reçu — {piece.libelle}",
            titre="Votre document a bien été reçu",
            message=(
                f"Bonjour {dossier.prenom},\n\n"
                f"Le document « {piece.libelle} » a bien été transmis. "
                "Le secrétariat va maintenant le vérifier."
            ),
            lien=suivi_url,
            libelle_lien="Suivre mon dossier",
            destinataires=[dossier.email],
        )
        notifier_plusieurs(
            User.objects.filter(
                is_active=True,
                role__in=[User.Role.ADMIN, User.Role.SECRETARIAT],
            ),
            f"Pièce déposée — {dossier.nom_complet}",
            type_notification=Notification.Type.CANDIDATURE,
            message=(
                f"{dossier.nom_complet} a déposé la pièce « {piece.libelle} » réclamée à son dossier. "
                "Elle attend une vérification."
            ),
            details=[
                {"libelle": "Candidat", "valeur": dossier.nom_complet},
                {"libelle": "Pièce déposée", "valeur": piece.libelle},
            ],
            url_cible=reverse("administration:candidature_detail", kwargs={"pk": dossier.pk}),
        )
        messages.success(request, f"« {piece.libelle} » a bien été transmis. Le secrétariat va le vérifier.")
    else:
        for erreurs in formulaire.errors.values():
            messages.error(request, erreurs[0])

    return redirect("admissions:candidature_suivi", token=token)


def parcours_preview(request):
    """Retourne un encart de prévisualisation du parcours choisi pour le formulaire HTMX."""
    parcours_id = request.GET.get("parcours")
    parcours = None
    if parcours_id:
        parcours = get_object_or_404(Parcours.objects.filter(actif=True), pk=parcours_id)
    return render(request, "admissions/partials/parcours_preview.html", {"parcours": parcours})
