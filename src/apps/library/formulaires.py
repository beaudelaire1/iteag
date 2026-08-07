"""Formulaires de gestion de la bibliothèque."""

from django import forms
from django.core.exceptions import ValidationError

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
        cote = (self.cleaned_data.get("cote") or "").strip()
        if not cote:
            return cote
        doublon = NoticeBibliographique.objects.filter(cote__iexact=cote).exclude(pk=self.instance.pk)
        if doublon.exists():
            raise forms.ValidationError(f"La cote « {cote} » est déjà portée par « {doublon.first().titre} ».")
        return cote

    def clean_isbn(self):
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
        self.fields["emprunteur"].label_from_instance = lambda obj: (
            f"{obj.get_full_name()} ({obj.email})" if obj.get_full_name() else f"{obj.username} ({obj.email})"
        )

    def clean(self):
        cleaned_data = super().clean()
        emprunteur = cleaned_data.get("emprunteur")
        statut = cleaned_data.get("statut")
        if emprunteur is None:
            return cleaned_data

        verifier = not self.instance.pk
        if self.instance.pk:
            original = Emprunt.objects.only("emprunteur_id", "statut").get(pk=self.instance.pk)
            statuts_actifs = {
                Emprunt.Statut.RESERVE,
                Emprunt.Statut.EN_COURS,
                Emprunt.Statut.EN_RETARD,
            }
            verifier = original.emprunteur_id != emprunteur.pk or (
                original.statut not in statuts_actifs and statut in statuts_actifs
            )

        if not verifier:
            return cleaned_data

        from apps.library import services

        try:
            services.verifier_droit_emprunt(emprunteur)
        except ValidationError as erreur:
            self.add_error("emprunteur", erreur.messages[0])
        return cleaned_data
