from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render

from apps.formations.models import Parcours

from .emails import send_candidature_confirmation
from .forms import CandidatureForm
from .models import DossierCandidature
from .services import deposer_piece


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
    """Suivi public du dossier, et dépôt des pièces réclamées.

    Le candidat n'a pas de compte : le jeton du lien est son seul titre. Il ne
    donne accès qu'à ce dossier-là, et ne permet que de déposer une pièce
    explicitement demandée — jamais d'en ajouter une de sa propre initiative,
    ni de modifier quoi que ce soit d'autre.
    """
    dossier = get_object_or_404(
        DossierCandidature.objects.prefetch_related("pieces_complementaires"),
        token_suivi=token,
    )

    if request.method == "POST":
        piece = get_object_or_404(
            dossier.pieces_complementaires,
            pk=request.POST.get("piece"),
        )
        fichier = request.FILES.get("fichier")
        if fichier is None:
            messages.error(request, "Choisissez un fichier à déposer.")
        else:
            try:
                deposer_piece(piece, fichier)
            except ValidationError as erreur:
                messages.error(request, erreur.messages[0])
            else:
                messages.success(
                    request,
                    f"« {piece.libelle} » a bien été déposée. Le secrétariat la vérifiera.",
                )
        return redirect("admissions:candidature_suivi", token=token)

    pieces = list(dossier.pieces_complementaires.all())
    return render(
        request,
        "admissions/candidature_suivi.html",
        {
            "dossier": dossier,
            "pieces": pieces,
            "pieces_attendues": [piece for piece in pieces if piece.est_en_attente],
        },
    )


def parcours_preview(request):
    """Retourne un encart de prévisualisation du parcours choisi pour le formulaire HTMX."""
    parcours_id = request.GET.get("parcours")
    parcours = None
    if parcours_id:
        parcours = get_object_or_404(Parcours.objects.filter(actif=True), pk=parcours_id)
    return render(request, "admissions/partials/parcours_preview.html", {"parcours": parcours})
