from django import forms

from apps.academics.models import CoursDeSession
from apps.core.formulaires import FormulaireModeleITEAG

from .models import Annonce, Evaluation, RessourcePedagogique

# Classes du système de design ITEAG (assets/css/input.css).
# Les formulaires du portail enseignant utilisent les mêmes composants que le
# reste du site : pas de classes Tailwind ad hoc, pas de palette parallèle.
INPUT = "form-input"
INPUT_COURT = "form-input w-24"
FICHIER = "form-file"


class RessourceUploadForm(FormulaireModeleITEAG):
    """ENS-002 — Upload de ressource pédagogique."""

    class Meta:
        model = RessourcePedagogique
        fields = ["titre", "description", "fichier", "visible_etudiants"]
        widgets = {
            "titre": forms.TextInput(attrs={"class": INPUT}),
            "description": forms.Textarea(attrs={"rows": 3, "class": INPUT}),
            "fichier": forms.ClearableFileInput(attrs={"class": FICHIER}),
        }


class GradeForm(FormulaireModeleITEAG):
    """ENS-004 — Saisie de note par l'enseignant."""

    class Meta:
        model = Evaluation
        fields = ["note", "appreciation", "ects_valides", "fichier_corrige"]
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
            "fichier_corrige": forms.ClearableFileInput(attrs={"accept": ".pdf,.doc,.docx,.odt,.jpg,.png"}),
        }

    def clean_note(self):
        note = self.cleaned_data.get("note")
        if note is None:
            raise forms.ValidationError("La note est obligatoire.")
        return note


class AnnonceForm(FormulaireModeleITEAG):
    """ENS-006 — Publication d'annonce."""

    class Meta:
        model = Annonce
        fields = ["titre", "contenu"]
        widgets = {
            "titre": forms.TextInput(attrs={"class": INPUT, "placeholder": "Titre de l'annonce"}),
            "contenu": forms.Textarea(attrs={"rows": 5, "class": INPUT, "placeholder": "Contenu de l'annonce…"}),
        }


class ParametresEvaluationForm(FormulaireModeleITEAG):
    """Date d'examen et fenêtre de remise, fixées par l'enseignant.

    Ces trois réglages vivent sur le cours de session et non sur chaque copie :
    une échéance se décide pour la classe, pas étudiant par étudiant.
    """

    class Meta:
        model = CoursDeSession
        fields = ["date_examen", "depot_ouverture", "depot_fermeture"]
        widgets = {
            "date_examen": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
            "depot_ouverture": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
            "depot_fermeture": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Sans ce format, un champ « datetime-local » ne réaffiche pas la valeur
        # déjà enregistrée : l'enseignant croit son réglage perdu et le ressaisit.
        for nom in ("date_examen", "depot_ouverture", "depot_fermeture"):
            self.fields[nom].input_formats = ["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"]

    def clean(self):
        donnees = super().clean()
        ouverture, fermeture = donnees.get("depot_ouverture"), donnees.get("depot_fermeture")
        if ouverture and fermeture and fermeture < ouverture:
            self.add_error("depot_fermeture", "La fermeture ne peut pas précéder l'ouverture.")
        return donnees
