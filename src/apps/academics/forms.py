from pathlib import Path

from django import forms

from apps.academics.models import DemandeInscriptionCours
from apps.core.formulaires import FormulaireModeleITEAG
from apps.lms.models import Evaluation


class StudentSubmissionForm(FormulaireModeleITEAG):
    class Meta:
        model = Evaluation
        fields = ["fichier_soumis"]
        widgets = {
            "fichier_soumis": forms.ClearableFileInput(attrs={"class": "form-file", "accept": ".pdf,.doc,.docx,.odt"})
        }

    def clean_fichier_soumis(self):
        uploaded = self.cleaned_data.get("fichier_soumis")
        if not uploaded:
            raise forms.ValidationError("Sélectionnez le fichier à remettre.")
        if uploaded.size > 10 * 1024 * 1024:
            raise forms.ValidationError("Le fichier ne doit pas dépasser 10 Mo.")
        if Path(uploaded.name).suffix.lower() not in {".pdf", ".doc", ".docx", ".odt"}:
            raise forms.ValidationError("Formats acceptés : PDF, DOC, DOCX ou ODT.")
        return uploaded


class EnrollmentRequestForm(FormulaireModeleITEAG):
    class Meta:
        model = DemandeInscriptionCours
        fields = ["note_etudiant", "reference_paiement", "justificatif_paiement"]
        widgets = {
            "note_etudiant": forms.Textarea(
                attrs={
                    "class": "form-input",
                    "rows": 4,
                    "placeholder": "Précisez si nécessaire votre objectif ou une contrainte particulière.",
                }
            ),
            "reference_paiement": forms.TextInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "Référence de virement ou de reçu, si le règlement est déjà effectué",
                }
            ),
            "justificatif_paiement": forms.ClearableFileInput(
                attrs={"class": "form-file", "accept": ".pdf,.jpg,.jpeg,.png"}
            ),
        }

    def clean_justificatif_paiement(self):
        uploaded = self.cleaned_data.get("justificatif_paiement")
        if not uploaded:
            return uploaded
        if uploaded.size > 5 * 1024 * 1024:
            raise forms.ValidationError("Le justificatif ne doit pas dépasser 5 Mo.")
        if Path(uploaded.name).suffix.lower() not in {".pdf", ".jpg", ".jpeg", ".png"}:
            raise forms.ValidationError("Formats acceptés : PDF, JPG ou PNG.")
        return uploaded
