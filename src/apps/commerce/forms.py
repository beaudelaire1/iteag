from django import forms
from django.utils.text import slugify

from apps.commerce.models import Commande, ProduitLivre
from apps.core.formulaires import FormulaireITEAG, FormulaireModeleITEAG


class AjouterPanierForm(FormulaireITEAG):
    quantite = forms.IntegerField(min_value=1, max_value=99, initial=1, label="Quantité")


class CommandeForm(FormulaireITEAG):
    prenom = forms.CharField(max_length=100, label="Prénom")
    nom = forms.CharField(max_length=100)
    email = forms.EmailField()
    telephone = forms.CharField(max_length=30, required=False, label="Téléphone")
    adresse = forms.CharField(max_length=250)
    complement_adresse = forms.CharField(max_length=250, required=False, label="Complément d'adresse")
    code_postal = forms.CharField(max_length=20, label="Code postal")
    ville = forms.CharField(max_length=120)
    pays = forms.CharField(max_length=100, initial="Guadeloupe")
    mode_paiement = forms.ChoiceField(choices=Commande.ModePaiement.choices, label="Mode de règlement")
    commentaire = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}))
    accepte_conditions = forms.BooleanField(label="J'accepte les conditions de vente et confirme ma commande.")
    site_web = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"tabindex": "-1", "autocomplete": "off", "aria-hidden": "true"}),
        label="",
    )

    def __init__(self, *args, utilisateur=None, **kwargs):
        super().__init__(*args, **kwargs)
        if utilisateur is not None and getattr(utilisateur, "is_authenticated", False) and not self.is_bound:
            self.initial.update(
                {
                    "prenom": utilisateur.first_name,
                    "nom": utilisateur.last_name,
                    "email": utilisateur.email,
                    "telephone": getattr(utilisateur, "phone", ""),
                }
            )

    def clean_site_web(self):
        if self.cleaned_data.get("site_web"):
            raise forms.ValidationError("La commande n'a pas pu être validée.")
        return ""


class ProduitLivreForm(FormulaireModeleITEAG):
    class Meta:
        model = ProduitLivre
        fields = [
            "notice",
            "titre",
            "slug",
            "sku",
            "isbn",
            "auteur",
            "description",
            "prix_ttc",
            "image",
            "poids_grammes",
            "stock_physique",
            "seuil_alerte",
            "actif",
        ]
        widgets = {"description": forms.Textarea(attrs={"rows": 5})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["slug"].required = False
        self.fields["slug"].help_text = "Laisser vide pour le générer depuis le titre."
        if not self.instance._state.adding:
            self.fields["stock_physique"].disabled = True
            self.fields[
                "stock_physique"
            ].help_text = "Utilisez l'ajustement de stock afin de conserver une trace du mouvement."

    def clean_slug(self):
        slug = self.cleaned_data.get("slug") or slugify(self.cleaned_data.get("titre", ""))
        return slug[:300]

    def clean_stock_physique(self):
        stock = self.cleaned_data["stock_physique"]
        if not self.instance._state.adding and stock < self.instance.stock_reserve:
            raise forms.ValidationError(
                f"{self.instance.stock_reserve} exemplaire(s) sont réservés : le stock ne peut pas être inférieur."
            )
        return stock


class AjustementStockForm(FormulaireITEAG):
    variation = forms.IntegerField(
        min_value=-100000,
        max_value=100000,
        label="Variation",
        help_text="Ex. 5 pour une entrée, -2 pour corriger un écart.",
    )
    motif = forms.CharField(max_length=250, label="Motif")
