from django import forms

from apps.core.formulaires import FormulaireITEAG


class TemoignageEtudiantForm(FormulaireITEAG):
    texte = forms.CharField(
        min_length=30,
        max_length=2000,
        label="Votre témoignage",
        help_text="Parlez de votre expérience à l'ITEAG avec vos propres mots. 2 000 caractères maximum.",
        widget=forms.Textarea(attrs={"rows": 8, "placeholder": "Ce que l'ITEAG m'a apporté…"}),
    )
    consentement_publication = forms.BooleanField(
        label="J'autorise l'ITEAG à publier ce témoignage avec mon nom et ma promotion.",
    )

    def clean_texte(self):
        return (self.cleaned_data.get("texte") or "").strip()
