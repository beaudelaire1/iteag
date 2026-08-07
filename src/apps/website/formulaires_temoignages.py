from django import forms

from apps.core.editeur_riche import ChampTexteRiche
from apps.core.formulaires import FormulaireITEAG
from apps.core.services.redaction import assainir, en_texte


class TemoignageEtudiantForm(FormulaireITEAG):
    texte = ChampTexteRiche(
        max_length=6000,
        label="Votre témoignage",
        help_text=(
            "Parlez de votre expérience à l'ITEAG avec vos propres mots. "
            "Vous pouvez utiliser le gras et l'italique ; 2 000 caractères de texte maximum."
        ),
        placeholder="Ce que l'ITEAG m'a apporté…",
        min_height="12rem",
        features=("bold", "italic"),
    )
    photo = forms.ImageField(
        required=False,
        label="Photo du témoignage",
        help_text=(
            "Facultative. Choisissez la photo que vous souhaitez voir avec ce témoignage ; "
            "elle peut être différente de votre photo de profil. 5 Mo maximum."
        ),
        widget=forms.ClearableFileInput(attrs={"class": "form-file", "accept": "image/*"}),
    )
    supprimer_photo = forms.BooleanField(
        required=False,
        label="Retirer la photo actuellement associée à mon témoignage",
    )
    consentement_publication = forms.BooleanField(
        label=(
            "J'autorise l'ITEAG à publier ce témoignage avec mon nom, ma promotion "
            "et, si j'en ai choisi une, la photo associée."
        ),
    )

    def clean_texte(self):
        texte = assainir(self.cleaned_data.get("texte") or "")
        texte_seul = en_texte(texte)
        if len(texte_seul) < 30:
            raise forms.ValidationError("Votre témoignage doit contenir au moins 30 caractères.")
        if len(texte_seul) > 2000:
            raise forms.ValidationError("Votre témoignage ne peut pas dépasser 2 000 caractères.")
        return texte

    def clean_photo(self):
        photo = self.cleaned_data.get("photo")
        if photo and photo.size > 5 * 1024 * 1024:
            raise forms.ValidationError("La photo ne peut pas dépasser 5 Mo.")
        return photo
