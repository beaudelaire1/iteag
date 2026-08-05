"""Formulaires de rédaction d'un article de recherche."""

from django import forms

from apps.core.editeur_riche import ChampTexteRiche
from apps.core.formulaires import FormulaireModeleITEAG
from apps.website.models_publications import Article, ImageArticle

INPUT = "form-input"
FICHIER = "form-file"


class ArticleForm(FormulaireModeleITEAG):
    """Titre, sous-titre, corps Draftail et image à la une."""

    corps = ChampTexteRiche(
        required=False,
        label="Corps de l'article",
        placeholder="Rédigez votre article ici…",
        min_height="24rem",
        help_text=(
            "Titres, emphases, listes, citations, liens et alignements sont conservés. "
            "Les styles parasites issus d'un collage sont retirés à l'enregistrement."
        ),
    )

    class Meta:
        model = Article
        fields = ["titre", "sous_titre", "chapeau", "corps", "image_principale", "credit_image", "mots_cles"]
        widgets = {
            "titre": forms.TextInput(
                attrs={"class": INPUT, "placeholder": "L'ecclésiologie dans les Épîtres pastorales"}
            ),
            "sous_titre": forms.TextInput(
                attrs={"class": INPUT, "placeholder": "Ce que Paul dit de l'organisation de l'Église"}
            ),
            "chapeau": forms.Textarea(
                attrs={"rows": 3, "class": INPUT, "placeholder": "Deux ou trois phrases d'accroche…"}
            ),
            "image_principale": forms.ClearableFileInput(attrs={"class": FICHIER, "accept": "image/*"}),
            "credit_image": forms.TextInput(attrs={"class": INPUT, "placeholder": "© Nom du photographe"}),
            "mots_cles": forms.TextInput(attrs={"class": INPUT, "placeholder": "ecclésiologie, épîtres, Paul"}),
        }

    def clean_titre(self):
        titre = (self.cleaned_data.get("titre") or "").strip()
        if not titre:
            raise forms.ValidationError("Un article a besoin d'un titre.")
        return titre


class IllustrationForm(FormulaireModeleITEAG):
    class Meta:
        model = ImageArticle
        fields = ["fichier", "legende"]
        widgets = {
            "fichier": forms.ClearableFileInput(attrs={"class": FICHIER, "accept": "image/*"}),
            "legende": forms.TextInput(attrs={"class": INPUT, "placeholder": "Légende de la figure"}),
        }
