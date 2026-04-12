from django import forms

from .models import DossierCandidature


class CandidatureForm(forms.ModelForm):
    """Formulaire public multi-étapes de candidature — PUB-011."""

    class Meta:
        model = DossierCandidature
        fields = [
            "nom",
            "prenom",
            "email",
            "telephone",
            "date_naissance",
            "parcours_souhaite",
            "motivations",
            "eglise",
            "eglise_fondatrice",
            "piece_identite",
            "diplomes",
            "autre_document",
        ]
        widgets = {
            "motivations": forms.Textarea(attrs={"rows": 5}),
            "date_naissance": forms.DateInput(attrs={"type": "date"}),
        }
