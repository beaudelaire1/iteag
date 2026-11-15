"""Dépôt d'une brochure au catalogue, depuis le portail de gestion.

Le secrétariat ne compose pas la brochure ici : elle arrive mise en page. Le
formulaire n'a donc qu'un travail, mais il doit le faire sérieusement —
vérifier que le contenu du fichier correspond bien à ce que son nom annonce, et
refuser tout de suite ce qui ne s'ouvrirait pas chez le visiteur.
"""

from django import forms
from django.core.files.uploadedfile import SimpleUploadedFile

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


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    widget = MultipleFileInput

    def clean(self, data, initial=None):
        nettoyer = super().clean
        if isinstance(data, (list, tuple)):
            return [nettoyer(fichier, initial) for fichier in data]
        return [nettoyer(data, initial)] if data else []


class BrochureForm(FormulaireModeleITEAG):
    images = MultipleFileField(
        required=False,
        label="Images PNG — une image par page",
        help_text="Sélectionnez autant de PNG que nécessaire. Chaque image deviendra une page du PDF, dans l'ordre de sélection.",
        widget=MultipleFileInput(attrs={"class": FICHIER, "accept": ".png,image/png"}),
    )

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
            "couverture": (
                "Facultative. Elle illustre la vignette sur la page publique. "
                "Inutile pour une affiche déposée en JPG, PNG ou WebP : elle s'illustre elle-même."
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # À la modification, le fichier déjà en place suffit : réclamer un
        # nouveau dépôt pour corriger une faute de frappe dans le titre serait
        # absurde, et pousserait à re-téléverser vingt mégaoctets pour rien.
        self.fields["fichier"].required = False

    def clean_fichier(self):
        depose = self.cleaned_data.get("fichier")
        if not depose:
            # Champ laissé vide à la modification : on garde le fichier en place.
            if self.instance.pk and self.instance.fichier:
                return self.instance.fichier
            return None
        # Un fichier inchangé revient sous la forme du champ enregistré, qui
        # n'a ni « content_type » ni curseur à repositionner : le contrôle ne
        # s'applique qu'à un dépôt réel.
        if not hasattr(depose, "content_type"):
            return depose
        return valider_fichier(depose, REGLE_BROCHURE)

    def clean_images(self):
        images = self.cleaned_data.get("images") or []
        valides = []
        for image in images:
            if image.size > REGLE_BROCHURE.taille_max:
                raise forms.ValidationError(
                    f"« {image.name} » dépasse la limite de {REGLE_BROCHURE.taille_max_lisible}."
                )
            if not image.name.lower().endswith(".png"):
                raise forms.ValidationError(f"« {image.name} » n'est pas un fichier PNG.")
            valides.append(valider_fichier(image, REGLE_BROCHURE))
        return valides

    def clean(self):
        donnees = super().clean()
        images = donnees.get("images") or []
        fichier = donnees.get("fichier")
        nouveau_fichier = fichier is not None and hasattr(fichier, "content_type")
        if images and nouveau_fichier:
            self.add_error("images", "Choisissez soit un fichier, soit plusieurs images PNG, pas les deux.")
        if not images and not fichier and not (self.instance.pk and self.instance.fichier):
            self.add_error("fichier", "Choisissez un document ou importez une ou plusieurs images PNG.")
        return donnees

    def pdf_depuis_images(self):
        """Assemble chaque PNG en une page du PDF de la brochure."""
        images = self.cleaned_data.get("images") or []
        if not images:
            return None

        import io
        from PIL import Image, ImageOps

        pages = []
        for fichier in images:
            fichier.seek(0)
            with Image.open(fichier) as source:
                page = ImageOps.exif_transpose(source).convert("RGB")
                page.load()
                pages.append(page.copy())

        sortie = io.BytesIO()
        premiere, *suivantes = pages
        premiere.save(sortie, format="PDF", save_all=True, append_images=suivantes, resolution=150.0)
        for page in pages:
            page.close()
        return SimpleUploadedFile("brochure-images.pdf", sortie.getvalue(), content_type="application/pdf")

    def clean_couverture(self):
        image = self.cleaned_data.get("couverture")
        if image and getattr(image, "size", 0) > 5 * 1024 * 1024:
            raise forms.ValidationError("L'image de couverture ne peut pas dépasser 5 Mo.")
        return image
