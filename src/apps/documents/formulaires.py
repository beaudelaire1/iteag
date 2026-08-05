"""Formulaire de rédaction d'un document officiel.

Un « ModelForm », contrairement aux actualités : « DocumentRedige » est un
modèle Django ordinaire, qui s'enregistre en s'enregistrant. Rien n'oblige ici
à passer par une vue pour placer l'objet.

Le corps emprunte l'éditeur partagé — « apps/core/editeur_riche.py » — plutôt
qu'un « textarea » : un courrier officiel porte des paragraphes, des listes et
des alignements, et la personne qui l'écrit ne connaît pas le HTML.
"""

from django import forms

from apps.core.editeur_riche import ChampTexteRiche
from apps.core.formulaires import FormulaireModeleITEAG
from apps.core.services.redaction import en_texte
from apps.documents.models import DocumentRedige

INPUT = "form-input"


class DocumentRedigeForm(FormulaireModeleITEAG):
    corps = ChampTexteRiche(
        required=False,
        label="Corps du document",
        placeholder="Rédigez le document ici…",
        min_height="24rem",
        help_text="Le même éditeur que les actualités et les articles. La signature s'ajoute plus bas.",
    )

    class Meta:
        model = DocumentRedige
        # « genre » n'y figure pas : il est choisi à la création et n'en bouge
        # plus. En changer reviendrait à demander à une convocation les champs
        # d'un compte rendu, et la fiche déjà remplie n'aurait plus de sens.
        fields = [
            "titre",
            "date_document",
            "objet",
            "destinataire_nom",
            "destinataire_adresse",
            "corps",
            "signataire_nom",
            "signataire_qualite",
        ]
        widgets = {
            "titre": forms.TextInput(attrs={"class": INPUT, "placeholder": "Convocation du conseil pédagogique"}),
            "date_document": forms.DateInput(attrs={"class": INPUT, "type": "date"}, format="%Y-%m-%d"),
            "objet": forms.TextInput(attrs={"class": INPUT, "placeholder": "Convocation à la séance du 12 septembre"}),
            "destinataire_nom": forms.TextInput(
                attrs={"class": INPUT, "placeholder": "Monsieur le Pasteur Jean Dupont"}
            ),
            "destinataire_adresse": forms.Textarea(
                attrs={"rows": 3, "class": INPUT, "placeholder": "Adresse postale, une ligne par ligne"}
            ),
            "signataire_nom": forms.TextInput(attrs={"class": INPUT, "placeholder": "Alain Nisus"}),
            "signataire_qualite": forms.TextInput(attrs={"class": INPUT, "placeholder": "Directeur"}),
        }

    def __init__(self, *args, fiche=None, **kwargs):
        super().__init__(*args, **kwargs)
        # « date_document » a une valeur par défaut au niveau du modèle ; sans
        # ce format, le champ « type=date » du navigateur reçoit « 4 août 2026 »
        # et s'affiche vide, ce qui donne l'impression que la date est perdue.
        self.fields["date_document"].input_formats = ["%Y-%m-%d"]

        # Le corps ne s'appelle pas pareil selon le genre : « corps de la
        # lettre » pour un courrier, « compte rendu des débats » pour un
        # compte rendu. Un intitulé juste vaut mieux qu'une aide à lire.
        if fiche is not None:
            self.fields["corps"].label = fiche.intitule_corps
            self.fields["corps"].widget.options["placeholder"] = fiche.invite_corps
            self.fields["corps"].widget.options["ariaLabel"] = fiche.intitule_corps

    def clean_titre(self):
        titre = (self.cleaned_data.get("titre") or "").strip()
        if not titre:
            raise forms.ValidationError("Donnez un titre interne : c'est ce qui vous le fera retrouver.")
        return titre

    def clean_objet(self):
        objet = (self.cleaned_data.get("objet") or "").strip()
        if not objet:
            raise forms.ValidationError("Un document officiel porte un objet.")
        return objet

    def clean_corps(self):
        """Le brouillon accepte un corps vide ; la finalisation, non.

        On écrit rarement un courrier d'un seul jet : enregistrer un début de
        texte doit rester possible. C'est « finaliser() » qui exige un corps,
        au moment où le document devient un acte.
        """
        corps = self.cleaned_data.get("corps") or ""
        return corps if en_texte(corps).strip() else ""
