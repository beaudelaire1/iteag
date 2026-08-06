"""Formulaire de saisie d'une notice de bibliothèque."""

from django import forms

from apps.core.formulaires import FormulaireModeleITEAG
from apps.library.models import Emprunt, NoticeBibliographique


class NoticeForm(FormulaireModeleITEAG):
    """Saisie et correction d'une notice par le secrétariat."""

    class Meta:
        model = NoticeBibliographique
        fields = [
            "titre",
            "auteur",
            "editeur",
            "date_publication",
            "isbn",
            "cote",
            "discipline",
            "mots_cles",
            "description",
            "disponible",
        ]
        widgets = {
            "mots_cles": forms.Textarea(attrs={"rows": 2}),
            "description": forms.Textarea(attrs={"rows": 4}),
            "date_publication": forms.TextInput(attrs={"placeholder": "2009"}),
        }
        help_texts = {
            "cote": "Emplacement en rayon. Sert aussi de référence unique de la notice.",
            "date_publication": "Année de parution, telle qu'elle figure sur l'ouvrage.",
            "mots_cles": "Séparés par des virgules. Ils alimentent la recherche du catalogue.",
            "disponible": "Décocher lorsque l'ouvrage est emprunté, égaré ou en reliure.",
        }

    def clean_cote(self):
        """La cote désigne un emplacement : deux notices ne peuvent la partager."""
        cote = (self.cleaned_data.get("cote") or "").strip()
        if not cote:
            return cote
        doublon = NoticeBibliographique.objects.filter(cote__iexact=cote).exclude(pk=self.instance.pk)
        if doublon.exists():
            raise forms.ValidationError(f"La cote « {cote} » est déjà portée par « {doublon.first().titre} ».")
        return cote

    def clean_isbn(self):
        """Un ISBN se saisit avec des tirets ou sans : on n'en garde que les chiffres."""
        isbn = (self.cleaned_data.get("isbn") or "").replace("-", "").replace(" ", "").strip()
        if isbn and not (isbn.replace("X", "").replace("x", "").isdigit() and len(isbn) in (10, 13)):
            raise forms.ValidationError("Un ISBN compte 10 ou 13 chiffres.")
        return isbn


class EmpruntForm(FormulaireModeleITEAG):
    """Saisie, création et modification manuelle d'un emprunt par le secrétariat."""

    class Meta:
        model = Emprunt
        fields = [
            "notice",
            "emprunteur",
            "statut",
            "date_retour_prevue",
            "commentaire",
        ]
        widgets = {
            "date_retour_prevue": forms.DateInput(attrs={"type": "date"}),
            "commentaire": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        from apps.accounts.models import User

        super().__init__(*args, **kwargs)
        if not self.instance.pk:
            self.fields["notice"].queryset = NoticeBibliographique.objects.filter(disponible=True)
        self.fields["emprunteur"].queryset = User.objects.all().order_by("last_name", "first_name", "username")
        self.fields["emprunteur"].label_from_instance = (
            lambda obj: f"{obj.get_full_name()} ({obj.email})"
            if obj.get_full_name()
            else f"{obj.username} ({obj.email})"
        )
