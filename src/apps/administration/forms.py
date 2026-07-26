from pathlib import Path

from django import forms
from django.contrib.auth.password_validation import validate_password

from apps.academics.models import CoursDeSession, DemandeInscriptionCours, Paiement, ProfilEtudiant, SessionAcademique
from apps.accounts.models import User
from apps.formations.models import Cours, Professeur


class AdminUserForm(forms.ModelForm):
    password1 = forms.CharField(
        label="Mot de passe",
        widget=forms.PasswordInput(attrs={"class": "form-input"}),
        required=False,
        help_text="Laisser vide pour ne pas modifier.",
    )

    class Meta:
        model = User
        fields = ["username", "first_name", "last_name", "email", "phone", "role", "is_active"]
        widgets = {
            "username": forms.TextInput(attrs={"class": "form-input"}),
            "first_name": forms.TextInput(attrs={"class": "form-input"}),
            "last_name": forms.TextInput(attrs={"class": "form-input"}),
            "email": forms.EmailInput(attrs={"class": "form-input"}),
            "phone": forms.TextInput(attrs={"class": "form-input"}),
            "role": forms.Select(attrs={"class": "form-input"}),
            "is_active": forms.CheckboxInput(attrs={"class": "h-4 w-4 rounded"}),
        }

    def save(self, commit=True):
        user = super().save(commit=False)
        pw = self.cleaned_data.get("password1")
        if pw:
            user.set_password(pw)
        if commit:
            user.save()
        return user

    def clean_password1(self):
        password = self.cleaned_data.get("password1")
        if password:
            validate_password(password, self.instance)
        return password


class AdminUserCreateForm(AdminUserForm):
    password1 = forms.CharField(
        label="Mot de passe",
        widget=forms.PasswordInput(attrs={"class": "form-input"}),
        required=True,
    )


class AdminSessionForm(forms.ModelForm):
    class Meta:
        model = SessionAcademique
        fields = ["nom", "periode", "annee_academique", "date_debut", "date_fin", "statut"]
        widgets = {
            "nom": forms.TextInput(attrs={"class": "form-input"}),
            "periode": forms.Select(attrs={"class": "form-input"}),
            "annee_academique": forms.TextInput(attrs={"class": "form-input", "placeholder": "2025-2026"}),
            "date_debut": forms.DateInput(attrs={"class": "form-input", "type": "date"}),
            "date_fin": forms.DateInput(attrs={"class": "form-input", "type": "date"}),
            "statut": forms.Select(attrs={"class": "form-input"}),
        }


class AdminProfesseurForm(forms.ModelForm):
    class Meta:
        model = Professeur
        fields = ["nom", "prenom", "slug", "specialite", "biographie", "photo", "disciplines", "user", "actif", "ordre"]
        widgets = {
            "nom": forms.TextInput(attrs={"class": "form-input"}),
            "prenom": forms.TextInput(attrs={"class": "form-input"}),
            "slug": forms.TextInput(attrs={"class": "form-input"}),
            "specialite": forms.TextInput(attrs={"class": "form-input"}),
            "biographie": forms.Textarea(attrs={"class": "form-input", "rows": 4}),
            "photo": forms.ClearableFileInput(attrs={"class": "form-input"}),
            "disciplines": forms.CheckboxSelectMultiple(),
            "user": forms.Select(attrs={"class": "form-input"}),
            "actif": forms.CheckboxInput(attrs={"class": "h-4 w-4 rounded"}),
            "ordre": forms.NumberInput(attrs={"class": "form-input", "min": 0}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["user"].queryset = User.objects.filter(role=User.Role.ENSEIGNANT)
        self.fields["user"].required = False


class AdminEtudiantForm(forms.ModelForm):
    class Meta:
        model = ProfilEtudiant
        fields = [
            "utilisateur",
            "parcours",
            "promotion",
            "numero_etudiant",
            "statut_inscription",
            "formule_tarif",
            "eglise_fondatrice",
        ]
        widgets = {
            "utilisateur": forms.Select(attrs={"class": "form-input"}),
            "parcours": forms.Select(attrs={"class": "form-input"}),
            "promotion": forms.Select(attrs={"class": "form-input"}),
            "numero_etudiant": forms.TextInput(attrs={"class": "form-input"}),
            "statut_inscription": forms.Select(attrs={"class": "form-input"}),
            "formule_tarif": forms.Select(attrs={"class": "form-input"}),
            "eglise_fondatrice": forms.CheckboxInput(attrs={"class": "h-4 w-4 rounded"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["utilisateur"].queryset = User.objects.filter(role=User.Role.ETUDIANT)


class AdminCoursForm(forms.ModelForm):
    class Meta:
        model = Cours
        fields = ["titre", "slug", "code", "discipline", "parcours", "description", "objectifs", "ects", "actif"]
        widgets = {
            "titre": forms.TextInput(attrs={"class": "form-input"}),
            "slug": forms.TextInput(attrs={"class": "form-input"}),
            "code": forms.TextInput(attrs={"class": "form-input"}),
            "discipline": forms.Select(attrs={"class": "form-input"}),
            "parcours": forms.CheckboxSelectMultiple(),
            "description": forms.Textarea(attrs={"class": "form-input", "rows": 5}),
            "objectifs": forms.Textarea(attrs={"class": "form-input", "rows": 5}),
            "ects": forms.NumberInput(attrs={"class": "form-input", "min": 0, "step": "0.5"}),
            "actif": forms.CheckboxInput(attrs={"class": "h-4 w-4 rounded"}),
        }


class CoursDeSessionForm(forms.ModelForm):
    class Meta:
        model = CoursDeSession
        fields = [
            "session",
            "cours",
            "enseignant",
            "modalite",
            "salle",
            "horaires",
            "statut",
            "capacite",
            "inscriptions_ouvertes",
            "date_limite_inscription",
            "frais_inscription",
            "informations_pratiques",
        ]
        widgets = {
            "session": forms.Select(attrs={"class": "form-input"}),
            "cours": forms.Select(attrs={"class": "form-input"}),
            "enseignant": forms.Select(attrs={"class": "form-input"}),
            "modalite": forms.Select(attrs={"class": "form-input"}),
            "salle": forms.TextInput(attrs={"class": "form-input"}),
            "horaires": forms.Textarea(attrs={"class": "form-input", "rows": 3}),
            "statut": forms.Select(attrs={"class": "form-input"}),
            "capacite": forms.NumberInput(attrs={"class": "form-input", "min": 1}),
            "inscriptions_ouvertes": forms.CheckboxInput(attrs={"class": "h-4 w-4 rounded"}),
            "date_limite_inscription": forms.DateInput(attrs={"class": "form-input", "type": "date"}),
            "frais_inscription": forms.NumberInput(attrs={"class": "form-input", "min": 0, "step": "0.01"}),
            "informations_pratiques": forms.Textarea(attrs={"class": "form-input", "rows": 4}),
        }


class PaiementForm(forms.ModelForm):
    class Meta:
        model = Paiement
        fields = ["etudiant", "session", "montant", "date_paiement", "mode", "statut", "reference", "recu_pdf"]
        widgets = {
            "etudiant": forms.Select(attrs={"class": "form-input"}),
            "session": forms.Select(attrs={"class": "form-input"}),
            "montant": forms.NumberInput(attrs={"class": "form-input", "min": 0, "step": "0.01"}),
            "date_paiement": forms.DateInput(attrs={"class": "form-input", "type": "date"}),
            "mode": forms.Select(attrs={"class": "form-input"}),
            "statut": forms.Select(attrs={"class": "form-input"}),
            "reference": forms.TextInput(attrs={"class": "form-input"}),
            "recu_pdf": forms.ClearableFileInput(attrs={"class": "form-file", "accept": ".pdf"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["etudiant"].queryset = ProfilEtudiant.objects.select_related("utilisateur").order_by(
            "utilisateur__last_name", "utilisateur__first_name"
        )
        self.fields["session"].queryset = SessionAcademique.objects.order_by("-date_debut")

    def clean_recu_pdf(self):
        uploaded = self.cleaned_data.get("recu_pdf")
        if not uploaded:
            return uploaded
        if uploaded.size > 5 * 1024 * 1024:
            raise forms.ValidationError("Le reçu ne doit pas dépasser 5 Mo.")
        if Path(uploaded.name).suffix.lower() != ".pdf":
            raise forms.ValidationError("Le reçu doit être un fichier PDF.")
        return uploaded


class EnrollmentDecisionForm(forms.Form):
    ACTIONS = [
        ("demander_paiement", "Valider administrativement et demander le paiement"),
        ("confirmer", "Confirmer l'inscription"),
        ("refuser", "Refuser la demande"),
        ("reouvrir", "Rouvrir la demande"),
    ]

    action = forms.ChoiceField(choices=ACTIONS, widget=forms.Select(attrs={"class": "form-input"}))
    paiement = forms.ModelChoiceField(
        queryset=Paiement.objects.none(),
        required=False,
        widget=forms.Select(attrs={"class": "form-input"}),
        help_text="Facultatif : le dernier paiement confirmé compatible sera sinon utilisé automatiquement.",
    )
    exonere_paiement = forms.BooleanField(
        required=False,
        label="Exonérer du paiement",
        widget=forms.CheckboxInput(attrs={"class": "h-4 w-4 rounded"}),
    )
    commentaire = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"class": "form-input", "rows": 4}),
        help_text="Obligatoire pour un refus ou une exonération.",
    )

    def __init__(self, *args, demande: DemandeInscriptionCours, **kwargs):
        super().__init__(*args, **kwargs)
        self.demande = demande
        self.fields["paiement"].queryset = Paiement.objects.filter(
            etudiant=demande.etudiant,
            session=demande.cours_session.session,
            statut=Paiement.StatutPaiement.CONFIRME,
        ).order_by("-date_paiement")
