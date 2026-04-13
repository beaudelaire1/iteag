from django import forms
from django.core.exceptions import ValidationError

from .models import DossierCandidature


class CandidatureForm(forms.ModelForm):
    """Formulaire public multi-étapes de candidature — PUB-011."""

    # Honeypot anti-spam : champ invisible pour les humains
    honeypot = forms.CharField(required=False, widget=forms.HiddenInput())

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

    def clean_honeypot(self):
        if self.cleaned_data.get("honeypot"):
            raise ValidationError("Soumission rejetée.")
        return ""
