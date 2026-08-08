from django import forms
from django.core.exceptions import ValidationError

from apps.core.formulaires import FormulaireModeleITEAG

from .formulaires import ACCEPT_PIECES, valider_fichier_piece
from .models import DossierCandidature


class CandidatureForm(FormulaireModeleITEAG):
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Les trois fichiers du dépôt initial sont des justificatifs au même
        # titre que ceux réclamés plus tard par le secrétariat. Ils appliquent
        # donc exactement le même contrat de format, taille et signature.
        for nom in ("piece_identite", "diplomes", "autre_document"):
            champ = self.fields[nom]
            champ.validators.append(valider_fichier_piece)
            champ.widget.attrs["accept"] = ACCEPT_PIECES

    def clean_honeypot(self):
        if self.cleaned_data.get("honeypot"):
            raise ValidationError("Soumission rejetée.")
        return ""
