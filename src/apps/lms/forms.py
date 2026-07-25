from django import forms

from .models import Annonce, Evaluation, RessourcePedagogique

# Classes du système de design ITEAG (assets/css/input.css).
# Les formulaires du portail enseignant utilisent les mêmes composants que le
# reste du site : pas de classes Tailwind ad hoc, pas de palette parallèle.
INPUT = "form-input"
INPUT_COURT = "form-input w-24"
FICHIER = "form-file"


class RessourceUploadForm(forms.ModelForm):
    """ENS-002 — Upload de ressource pédagogique."""

    class Meta:
        model = RessourcePedagogique
        fields = ["titre", "description", "fichier", "visible_etudiants"]
        widgets = {
            "titre": forms.TextInput(attrs={"class": INPUT}),
            "description": forms.Textarea(attrs={"rows": 3, "class": INPUT}),
            "fichier": forms.ClearableFileInput(attrs={"class": FICHIER}),
        }


class GradeForm(forms.ModelForm):
    """ENS-004 — Saisie de note par l'enseignant."""

    class Meta:
        model = Evaluation
        fields = ["note", "appreciation", "ects_valides"]
        widgets = {
            "note": forms.NumberInput(
                attrs={
                    "min": 0,
                    "max": 20,
                    "step": "0.5",
                    "class": INPUT_COURT,
                    "placeholder": "/20",
                }
            ),
            "appreciation": forms.Textarea(
                attrs={
                    "rows": 3,
                    "class": INPUT,
                    "placeholder": "Appréciation de l'enseignant…",
                }
            ),
            "ects_valides": forms.NumberInput(attrs={"min": 0, "max": 30, "step": "0.5", "class": INPUT_COURT}),
        }

    def clean_note(self):
        note = self.cleaned_data.get("note")
        if note is None:
            raise forms.ValidationError("La note est obligatoire.")
        return note


class AnnonceForm(forms.ModelForm):
    """ENS-006 — Publication d'annonce."""

    class Meta:
        model = Annonce
        fields = ["titre", "contenu"]
        widgets = {
            "titre": forms.TextInput(attrs={"class": INPUT, "placeholder": "Titre de l'annonce"}),
            "contenu": forms.Textarea(attrs={"rows": 5, "class": INPUT, "placeholder": "Contenu de l'annonce…"}),
        }
