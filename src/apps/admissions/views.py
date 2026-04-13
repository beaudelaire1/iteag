from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render

from apps.formations.models import Parcours

from .emails import send_candidature_confirmation
from .forms import CandidatureForm
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
    return render(request, "admissions/candidature_suivi.html", {"dossier": dossier})


def parcours_preview(request):
    """Retourne un encart de prévisualisation du parcours choisi pour le formulaire HTMX."""
    parcours_id = request.GET.get("parcours")
    parcours = None
    if parcours_id:
        parcours = get_object_or_404(Parcours.objects.filter(actif=True), pk=parcours_id)
    return render(request, "admissions/partials/parcours_preview.html", {"parcours": parcours})
