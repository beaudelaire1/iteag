"""
Habillage automatique des champs de formulaire.

Le défaut : chaque formulaire décidait lui-même de ses classes CSS, dans un
dictionnaire « widgets ». Ceux qui l'oubliaient — dont le formulaire public de
candidature, le plus visible du site — rendaient des champs bruts : bordure
d'un pixel gris clair, sans contraste, à peine visibles sur le fond crème de la
charte.

Le style est donc appliqué ici, en un seul endroit, à partir du type de widget.
Un formulaire qui pose déjà une classe garde la sienne : la règle complète, elle
ne remplace pas.
"""

from django import forms

# Une classe du système de composants par famille de widget.
CLASSES = {
    forms.Select: "form-select",
    forms.SelectMultiple: "form-select",
    forms.NullBooleanSelect: "form-select",
    forms.CheckboxInput: "form-checkbox",
    forms.CheckboxSelectMultiple: "form-checkbox",
    forms.RadioSelect: "form-checkbox",
    forms.ClearableFileInput: "form-file",
    forms.FileInput: "form-file",
}
CLASSE_PAR_DEFAUT = "form-input"

# Ces widgets n'ont pas de représentation visible : les habiller n'aurait pas
# de sens, et poserait une bordure autour du piège à robots.
INVISIBLES = (forms.HiddenInput, forms.MultipleHiddenInput)


def classe_attendue(widget) -> str:
    """Classe du système de composants correspondant à ce widget."""
    for type_widget, classe in CLASSES.items():
        if isinstance(widget, type_widget):
            return classe
    return CLASSE_PAR_DEFAUT


def habiller(formulaire) -> None:
    """Pose la classe manquante sur chaque champ.

    Rien n'est lu de « formulaire.errors » ici : y toucher depuis « __init__ »
    déclencherait la validation avant que la sous-classe ait fini de
    s'initialiser. L'état d'erreur est porté par le conteneur du champ, au
    rendu (voir « partials/champ.html »).
    """
    for champ in formulaire.fields.values():
        widget = champ.widget
        # Un champ retiré de l'arbre d'accessibilité n'est pas destiné à être
        # vu : l'habiller donnerait une bordure au piège à robots, qui cesserait
        # d'en être un.
        if isinstance(widget, INVISIBLES) or widget.attrs.get("aria-hidden") == "true":
            continue

        classes = widget.attrs.get("class", "").split()
        if not any(classe.startswith("form-") for classe in classes):
            classes.append(classe_attendue(widget))

        if champ.required:
            widget.attrs.setdefault("aria-required", "true")

        widget.attrs["class"] = " ".join(dict.fromkeys(classes))


class FormulaireITEAG(forms.Form):
    """Formulaire simple habillé à la charte."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        habiller(self)


class FormulaireModeleITEAG(forms.ModelForm):
    """Formulaire de modèle habillé à la charte."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        habiller(self)
