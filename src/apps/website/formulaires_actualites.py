"""Formulaire de rédaction d'une actualité.

Un formulaire simple, et non un « ModelForm » sur « NewsPage » : une page
Wagtail ne s'enregistre pas comme un modèle ordinaire — elle s'insère dans un
arbre, se versionne, se publie. Laisser un « ModelForm » appeler « save() »
produirait une page hors de l'arbre, invisible et sans URL. Le formulaire
recueille donc la saisie, et la vue fait le placement.

L'image est reçue en fichier plutôt qu'en choix parmi la médiathèque : la
personne qui écrit l'annonce a la photo sous la main, pas l'identifiant d'une
image déjà téléversée depuis Wagtail — auquel, précisément, elle n'a pas accès.
"""

from django import forms

from apps.core.editeur_riche import ChampTexteRiche
from apps.core.formulaires import FormulaireITEAG

INPUT = "form-input"


class ActualiteForm(FormulaireITEAG):
    titre = forms.CharField(
        max_length=250,
        label="Titre",
        widget=forms.TextInput(attrs={"class": INPUT, "placeholder": "Rentrée académique 2026"}),
    )
    date = forms.DateField(
        label="Date de publication",
        help_text="La date affichée sur le site. Elle ordonne la liste des actualités.",
        widget=forms.DateInput(attrs={"class": INPUT, "type": "date"}, format="%Y-%m-%d"),
    )
    chapeau = forms.CharField(
        required=False,
        max_length=500,
        label="Résumé",
        help_text="Deux ou trois phrases, affichées dans la liste des actualités et par les moteurs.",
        widget=forms.Textarea(attrs={"rows": 3, "class": INPUT, "placeholder": "Deux ou trois phrases…"}),
    )
    corps = ChampTexteRiche(
        required=False,
        label="Contenu de l'actualité",
        placeholder="Rédigez l'actualité ici…",
        min_height="20rem",
        help_text=(
            "Le même éditeur Wagtail est utilisé dans toute la plateforme ; "
            "le HTML est assaini côté serveur avant publication."
        ),
    )
    image = forms.ImageField(
        required=False,
        label="Image à la une",
        help_text="Facultative. Elle illustre la vignette dans la liste et le haut de l'actualité.",
        widget=forms.ClearableFileInput(attrs={"class": "form-file", "accept": "image/*"}),
    )

    def clean_titre(self):
        titre = (self.cleaned_data.get("titre") or "").strip()
        if not titre:
            raise forms.ValidationError("Une actualité a besoin d'un titre.")
        return titre

    def clean_corps(self):
        """Le corps est le seul contenu de l'annonce : une actualité vide n'annonce rien.

        La vérification porte sur le texte, pas sur le balisage : l'éditeur
        peut laisser un paragraphe vide quand on efface tout, et ce n'est pas
        du contenu.
        """
        from apps.core.services.redaction import en_texte

        corps = self.cleaned_data.get("corps") or ""
        if not en_texte(corps).strip():
            raise forms.ValidationError("Écrivez le contenu de l'actualité.")
        return corps
