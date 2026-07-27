from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

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
            dossier = form.save()
            send_candidature_confirmation(dossier)
            messages.success(request, "Votre candidature a bien été enregistrée.")
            return redirect("admissions:candidature_confirmation", token=dossier.token_suivi)
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
