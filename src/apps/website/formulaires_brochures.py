"""Dépôt d'une brochure au catalogue, depuis le portail de gestion.

Le secrétariat ne compose pas la brochure ici : elle arrive mise en page. Le
formulaire n'a donc qu'un travail, mais il doit le faire sérieusement —
vérifier que le contenu du fichier correspond bien à ce que son nom annonce, et
refuser tout de suite ce qui ne s'ouvrirait pas chez le visiteur.
"""

from django import forms

from apps.core.formulaires import FormulaireModeleITEAG
from apps.core.validation_fichiers import valider_fichier

# Le catalogue accepte exactement ce qu'accepte la brochure jointe à une
# actualité : mêmes formats, même plafond. Deux règles distinctes dériveraient
# au premier format ajouté d'un seul côté, et le secrétariat ne comprendrait
# pas qu'un DOCX passe par une porte et soit refusé par l'autre.
from apps.website.formulaires_actualites import REGLE_BROCHURE
from apps.website.models_publications import Brochure

INPUT = "form-input"
SELECT = "form-select"
FICHIER = "form-file"


class BrochureForm(FormulaireModeleITEAG):
    class Meta:
        model = Brochure
        fields = ["titre", "categorie", "description", "fichier", "couverture", "ordre"]
        widgets = {
            "titre": forms.TextInput(attrs={"class": INPUT, "placeholder": "Brochure de présentation de l'ITEAG 2026"}),
            "categorie": forms.Select(attrs={"class": SELECT}),
            "description": forms.Textarea(attrs={"class": INPUT, "rows": 3, "placeholder": "Deux ou trois phrases…"}),
            "fichier": forms.ClearableFileInput(attrs={"class": FICHIER, "accept": REGLE_BROCHURE.accept}),
            "couverture": forms.ClearableFileInput(attrs={"class": FICHIER, "accept": "image/*"}),
            "ordre": forms.NumberInput(attrs={"class": INPUT, "min": 0}),
        }
        help_texts = {
            "fichier": (
                f"{REGLE_BROCHURE.message_formats} {REGLE_BROCHURE.taille_max_lisible} au plus. "
                "En déposer un nouveau remplace le précédent."
            ),
            "couverture": "Facultative. Elle illustre la vignette sur la page publique.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # À la modification, le fichier déjà en place suffit : réclamer un
        # nouveau dépôt pour corriger une faute de frappe dans le titre serait
        # absurde, et pousserait à re-téléverser vingt mégaoctets pour rien.
        if self.instance.pk and self.instance.fichier:
            self.fields["fichier"].required = False

    def clean_fichier(self):
        depose = self.cleaned_data.get("fichier")
        if not depose:
            # Champ laissé vide à la modification : on garde le fichier en place.
            if self.instance.pk and self.instance.fichier:
                return self.instance.fichier
            raise forms.ValidationError("Choisissez le fichier de la brochure.")
        # Un fichier inchangé revient sous la forme du champ enregistré, qui
        # n'a ni « content_type » ni curseur à repositionner : le contrôle ne
        # s'applique qu'à un dépôt réel.
        if not hasattr(depose, "content_type"):
            return depose
        return valider_fichier(depose, REGLE_BROCHURE)

    def clean_couverture(self):
        image = self.cleaned_data.get("couverture")
        if image and getattr(image, "size", 0) > 5 * 1024 * 1024:
            raise forms.ValidationError("L'image de couverture ne peut pas dépasser 5 Mo.")
        return image
