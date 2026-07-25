from pathlib import Path

from django import forms

from apps.lms.models import Evaluation


class StudentSubmissionForm(forms.ModelForm):
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
