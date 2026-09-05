"""Formulaire de rédaction d'une actualité depuis le portail de gestion."""

from django import forms

from apps.core.editeur_riche import StreamFieldPortail
from apps.core.formulaires import FormulaireITEAG
from apps.core.services.redaction import assainir, en_texte
from apps.core.validation_fichiers import RegleFichier, valider_fichier
from apps.website.models_publications import ContenuActualite

INPUT = "form-input"
CHAMP_CONTENU = ContenuActualite._meta.get_field("contenu")

# Une brochure est un document à lire, pas une pièce à exécuter : la liste reste
# volontairement courte, et le contrôle porte sur la signature binaire, jamais
# sur la seule extension.
REGLE_BROCHURE = RegleFichier(
    extensions=frozenset({".pdf", ".docx", ".odt"}),
    taille_max=20 * 1024 * 1024,
    message_formats="Formats acceptés : PDF, DOCX ou ODT.",
)


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
            "Ajoutez le bloc qui correspond réellement au contenu : texte, important, tableau, procédure, "
            "chiffres clés, graphique simple, citation ou encadré."
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
    brochure = forms.FileField(
        required=False,
        label="Brochure ou document",
        help_text=(
            "Facultatif. PDF ou bureautique, 20 Mo au plus. Un bouton de téléchargement apparaît sous l'actualité."
        ),
        widget=forms.ClearableFileInput(attrs={"class": "form-file", "accept": REGLE_BROCHURE.accept}),
    )
    brochure_libelle = forms.CharField(
        required=False,
        max_length=200,
        label="Intitulé du document",
        help_text="Ce que le lecteur lira sur le bouton. À défaut : le nom du fichier.",
        widget=forms.TextInput(attrs={"class": INPUT, "placeholder": "Brochure Licence 2026-2027"}),
    )

    def clean_brochure(self):
        fichier = self.cleaned_data.get("brochure")
        if fichier:
            valider_fichier(fichier, REGLE_BROCHURE)
        return fichier

    def __init__(self, *args, **kwargs):
        """Laisse les anciens clients POSTer ``corps`` pendant la transition."""
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
            return CHAMP_CONTENU.stream_block.to_python([{"type": "texte", "value": assainir(corps_heritage)}])

        # Vide : c'est « clean » qui tranchera, une fois la brochure connue.
        # Le champ est nettoyé avant elle, il ne peut pas en décider seul.
        return contenu

    def clean(self):
        donnees = super().clean()
        # Une actualité doit porter quelque chose — mais pas forcément du texte.
        # Une brochure se publie sans un mot : « voici le programme de la
        # rentrée » n'ajoute rien au document lui-même, et l'exiger empêchait
        # purement et simplement de publier un PDF seul.
        if not donnees.get("contenu") and not donnees.get("brochure"):
            self.add_error(
                "contenu",
                "Ajoutez au moins un bloc de contenu, ou joignez une brochure.",
            )
        return donnees
