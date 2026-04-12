from django import forms

from .models import Annonce, Evaluation, RessourcePedagogique


class RessourceUploadForm(forms.ModelForm):
    """ENS-002 — Upload de ressource pédagogique."""

    class Meta:
        model = RessourcePedagogique
        fields = ["titre", "description", "fichier", "visible_etudiants"]
        widgets = {
            "titre": forms.TextInput(attrs={"class": "w-full rounded-lg border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 px-4 py-2.5 border text-sm"}),
            "description": forms.Textarea(attrs={"rows": 3, "class": "w-full rounded-lg border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 px-4 py-2.5 border text-sm"}),
            "fichier": forms.ClearableFileInput(attrs={"class": "block w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-semibold file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100"}),
        }


class GradeForm(forms.ModelForm):
    """ENS-004 — Saisie de note par l'enseignant."""

    class Meta:
        model = Evaluation
        fields = ["note", "appreciation", "ects_valides"]
        widgets = {
            "note": forms.NumberInput(attrs={"min": 0, "max": 20, "step": "0.5", "class": "w-24 rounded-lg border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 px-3 py-2 border text-sm", "placeholder": "/20"}),
            "appreciation": forms.Textarea(attrs={"rows": 3, "class": "w-full rounded-lg border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 px-4 py-2.5 border text-sm", "placeholder": "Appréciation de l'enseignant…"}),
            "ects_valides": forms.NumberInput(attrs={"min": 0, "max": 30, "step": "0.5", "class": "w-24 rounded-lg border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 px-3 py-2 border text-sm"}),
        }


class AnnonceForm(forms.ModelForm):
    """ENS-006 — Publication d'annonce."""

    class Meta:
        model = Annonce
        fields = ["titre", "contenu"]
        widgets = {
            "titre": forms.TextInput(attrs={"class": "w-full rounded-lg border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 px-4 py-2.5 border text-sm", "placeholder": "Titre de l'annonce"}),
            "contenu": forms.Textarea(attrs={"rows": 5, "class": "w-full rounded-lg border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 px-4 py-2.5 border text-sm", "placeholder": "Contenu de l'annonce…"}),
        }
