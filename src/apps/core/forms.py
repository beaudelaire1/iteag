from django import forms

from apps.accounts.models import User
from apps.academics.models import ProfilEtudiant, Promotion, SessionAcademique
from apps.formations.models import Professeur, Discipline


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
        fields = ["utilisateur", "parcours", "promotion", "numero_etudiant", "statut_inscription", "formule_tarif", "eglise_fondatrice"]
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
