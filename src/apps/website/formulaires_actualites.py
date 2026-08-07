"""Formulaire de rédaction d'une actualité depuis le portail de gestion."""

from django import forms

from apps.core.formulaires import FormulaireITEAG
from apps.website.models_publications import ContenuActualite

INPUT = "form-input"


class ActualiteForm(FormulaireITEAG):
    titre = forms.CharField(
        max_length=250,
        label="Titre",
        widget=forms.TextInput(attrs={"class": INPUT, "placeholder": "Rentrée académique 2026"}),
    )
    date = forms.DateField(
        label="Date de publication",
        help_text="La date affichée sur le site. Elle ordonne la liste des actualités.",
        widget=forms.DateInput(attrs={"class": INPUT, "type": "date"}, format="%Y-%m-%d"),
    )
    chapeau = forms.CharField(
        required=False,
        max_length=500,
        label="Résumé",
        help_text="Deux ou trois phrases, affichées dans la liste des actualités et par les moteurs.",
        widget=forms.Textarea(attrs={"rows": 3, "class": INPUT, "placeholder": "Deux ou trois phrases…"}),
    )
    contenu = ContenuActualite._meta.get_field("contenu").formfield(
        label="Contenu de l'actualité",
        help_text=(
            "Ajoutez uniquement les blocs utiles : texte, tableau, procédure, chiffres clés, "
            "graphique simple, citation ou encadré."
        ),
    )
    image = forms.ImageField(
        required=False,
        label="Image à la une",
        help_text="Facultative. Elle illustre la vignette dans la liste et le haut de l'actualité.",
        widget=forms.ClearableFileInput(attrs={"class": "form-file", "accept": "image/*"}),
    )

    def clean_titre(self):
        titre = (self.cleaned_data.get("titre") or "").strip()
        if not titre:
            raise forms.ValidationError("Une actualité a besoin d'un titre.")
        return titre

    def clean_contenu(self):
        contenu = self.cleaned_data.get("contenu")
        if not contenu:
            raise forms.ValidationError("Ajoutez au moins un bloc de contenu à l'actualité.")
        return contenu
