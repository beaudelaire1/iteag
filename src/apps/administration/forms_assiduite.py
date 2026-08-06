from django import forms

from apps.academics.models_assiduite import SeanceCours


class SeanceCoursForm(forms.ModelForm):
    class Meta:
        model = SeanceCours
        fields = ["date", "heure_debut", "heure_fin", "libelle"]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date", "class": "form-input"}),
            "heure_debut": forms.TimeInput(attrs={"type": "time", "class": "form-input"}),
            "heure_fin": forms.TimeInput(attrs={"type": "time", "class": "form-input"}),
            "libelle": forms.TextInput(
                attrs={"class": "form-input", "placeholder": "Ex. Cours du matin"}
            ),
        }

    def __init__(self, *args, cours_session, **kwargs):
        super().__init__(*args, **kwargs)
        self.cours_session = cours_session
        self.instance.cours_session = cours_session

    def clean_date(self):
        date = self.cleaned_data["date"]
        session = self.cours_session.session
        if not session.date_debut <= date <= session.date_fin:
            raise forms.ValidationError(
                "La séance doit être comprise dans les dates de la session académique."
            )
        return date

    def clean(self):
        cleaned_data = super().clean()
        debut = cleaned_data.get("heure_debut")
        fin = cleaned_data.get("heure_fin")
        if debut and fin and fin <= debut:
            self.add_error("heure_fin", "L'heure de fin doit suivre l'heure de début.")
        return cleaned_data
