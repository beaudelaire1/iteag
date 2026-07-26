from django import forms

from apps.core.formulaires import FormulaireITEAG
from apps.core.models import AbonneNewsletter


class NewsletterForm(FormulaireITEAG):
    """Inscription à la lettre d'information — CDC PUB-012."""

    email = forms.EmailField(
        label="Votre adresse email",
        widget=forms.EmailInput(attrs={"class": "form-input", "placeholder": "vous@exemple.org"}),
    )
    # Piège à robots : un humain ne remplit pas un champ qu'il ne voit pas.
    site_web = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"tabindex": "-1", "autocomplete": "off", "aria-hidden": "true"}),
        label="",
    )

    def clean_site_web(self):
        if self.cleaned_data.get("site_web"):
            raise forms.ValidationError("Envoi refusé.")
        return ""

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        existant = AbonneNewsletter.objects.filter(email=email).first()
        # Un abonné déjà confirmé et actif n'est pas une erreur : on le dira
        # dans la vue, sans révéler l'état de la liste à un tiers.
        self.abonne_existant = existant
        return email
