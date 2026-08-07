"""Formulaire de rédaction d'une actualité depuis le portail de gestion."""

from django import forms

from apps.core.editeur_riche import StreamFieldPortail
from apps.core.formulaires import FormulaireITEAG
from apps.core.services.redaction import assainir, en_texte
from apps.website.models_publications import ContenuActualite

INPUT = "form-input"
CHAMP_CONTENU = ContenuActualite._meta.get_field("contenu")


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
    contenu = CHAMP_CONTENU.formfield(
        label="Contenu de l'actualité",
        help_text=(
            "Ajoutez uniquement les blocs utiles : texte, tableau, procédure, chiffres clés, "
            "graphique simple, citation ou encadré."
        ),
        widget=StreamFieldPortail(CHAMP_CONTENU.stream_block),
    )
    # Compatibilité avec les anciennes requêtes/tests. Ce champ n'est jamais
    # montré dans la nouvelle interface ; s'il arrive encore, il devient un
    # bloc texte et passe par la même liste blanche que l'ancien éditeur.
    corps = forms.CharField(required=False, widget=forms.HiddenInput())
    image = forms.ImageField(
        required=False,
        label="Image à la une",
        help_text="Facultative. Elle illustre la vignette dans la liste et le haut de l'actualité.",
        widget=forms.ClearableFileInput(attrs={"class": "form-file", "accept": "image/*"}),
    )

    def __init__(self, *args, **kwargs):
        """Laisse les anciens clients POSTer ``corps`` pendant la transition.

        Un StreamField Wagtail attend normalement ses champs de gestion
        ``contenu-count`` avant même l'étape ``clean_*``. Les anciennes vues,
        intégrations et tests envoient seulement ``corps`` : on remplace alors
        le widget structuré par un champ caché pour cette requête précise. Le
        contenu historique est ensuite converti en bloc ``texte`` dans
        ``clean_contenu``. L'éditeur moderne reste inchangé pour tous les POST
        StreamField réels.
        """
        donnees = kwargs.get("data")
        if donnees is None and args:
            donnees = args[0]
        requete_heritage = donnees is not None and "contenu-count" not in donnees and "corps" in donnees

        super().__init__(*args, **kwargs)

        if requete_heritage:
            self.fields["contenu"] = forms.CharField(
                required=False,
                label="Contenu de l'actualité",
                widget=forms.HiddenInput(),
            )

    def clean_titre(self):
        titre = (self.cleaned_data.get("titre") or "").strip()
        if not titre:
            raise forms.ValidationError("Une actualité a besoin d'un titre.")
        return titre

    def clean_contenu(self):
        contenu = self.cleaned_data.get("contenu")
        if contenu:
            return contenu

        corps_heritage = self.data.get("corps") or ""
        if en_texte(corps_heritage).strip():
            bloc = ContenuActualite._meta.get_field("contenu").stream_block
            return bloc.to_python([{"type": "texte", "value": assainir(corps_heritage)}])

        raise forms.ValidationError("Ajoutez au moins un bloc de contenu à l'actualité.")
