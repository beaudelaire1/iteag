from django import forms

from apps.core.formulaires import FormulaireITEAG, FormulaireModeleITEAG

from .models import Annonce, Devoir, Evaluation, RessourcePedagogique

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


class AnnonceForm(FormulaireModeleITEAG):
    """ENS-006 — Publication d'annonce."""

    class Meta:
        model = Annonce
        fields = ["titre", "contenu"]
        widgets = {
            "titre": forms.TextInput(attrs={"class": INPUT, "placeholder": "Titre de l'annonce"}),
            "contenu": forms.Textarea(attrs={"rows": 5, "class": INPUT, "placeholder": "Contenu de l'annonce…"}),
        }


class DevoirForm(FormulaireModeleITEAG):
    """Le travail demandé : consigne, fenêtre de dépôt, barème."""

    class Meta:
        model = Devoir
        fields = [
            "titre",
            "type_evaluation",
            "modalite",
            "consigne",
            "fichier_consigne",
            "date_ouverture",
            "date_fermeture",
            "retard_accepte",
            "bareme",
            "ects",
        ]
        widgets = {
            "titre": forms.TextInput(attrs={"class": INPUT, "placeholder": "Dissertation sur l'épître aux Romains"}),
            "consigne": forms.Textarea(attrs={"rows": 6, "class": INPUT, "placeholder": "Ce qui est attendu…"}),
            "fichier_consigne": forms.ClearableFileInput(attrs={"class": FICHIER}),
            # « datetime-local » plutôt qu'un sélecteur maison : le navigateur
            # sait déjà proposer un calendrier, dans la langue de l'utilisateur,
            # et il reste utilisable au clavier.
            "date_ouverture": forms.DateTimeInput(
                attrs={"type": "datetime-local", "class": INPUT}, format="%Y-%m-%dT%H:%M"
            ),
            "date_fermeture": forms.DateTimeInput(
                attrs={"type": "datetime-local", "class": INPUT}, format="%Y-%m-%dT%H:%M"
            ),
            "bareme": forms.NumberInput(attrs={"min": 1, "step": "0.5", "class": INPUT_COURT}),
            "ects": forms.NumberInput(attrs={"min": 0, "max": 30, "step": "0.5", "class": INPUT_COURT}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for nom in ("date_ouverture", "date_fermeture"):
            self.fields[nom].input_formats = ["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"]

    def clean(self):
        donnees = super().clean()
        ouverture, fermeture = donnees.get("date_ouverture"), donnees.get("date_fermeture")
        if ouverture and fermeture and fermeture <= ouverture:
            self.add_error("date_fermeture", "La fermeture doit suivre l'ouverture.")
        return donnees


class RevisionNoteForm(FormulaireITEAG):
    """Recours sur une note publiée. Le motif n'est pas facultatif."""

    note = forms.DecimalField(
        min_value=0,
        max_value=20,
        decimal_places=2,
        label="Nouvelle note",
        widget=forms.NumberInput(attrs={"min": 0, "max": 20, "step": "0.5", "class": INPUT_COURT}),
    )
    appreciation = forms.CharField(
        required=False,
        label="Appréciation corrigée",
        widget=forms.Textarea(attrs={"rows": 3, "class": INPUT}),
    )
    motif = forms.CharField(
        label="Motif de la révision",
        help_text="Il est conservé, communiqué à l'étudiant, et consultable en cas de contestation.",
        widget=forms.Textarea(
            attrs={"rows": 3, "class": INPUT, "placeholder": "Erreur de report, seconde lecture, recours accordé…"}
        ),
    )

    def clean_motif(self):
        motif = self.cleaned_data["motif"].strip()
        if len(motif) < 10:
            raise forms.ValidationError("Précisez le motif : il devra tenir devant l'étudiant et devant le jury.")
        return motif
