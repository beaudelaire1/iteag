from django import forms
from django.contrib.auth import authenticate
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm
from django.core.exceptions import ValidationError

from apps.core.formulaires import FormulaireModeleITEAG, habiller
from apps.core.services.turnstile import MESSAGE_ECHEC, valider_requete

from .models import User


class EmailOrUsernameAuthenticationForm(AuthenticationForm):
    error_messages = {
        "invalid_login": "Identifiants invalides. Vérifiez votre email ou votre identifiant, puis votre mot de passe.",
        "inactive": "Ce compte est désactivé.",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Le formulaire d'authentification vient de Django : il ne connaît pas
        # la charte. On l'y rattache comme les autres.
        habiller(self)

    def clean(self):
        # Avant même de tenter l'authentification : un robot ne doit pas
        # pouvoir transformer ce point d'entrée en oracle de mots de passe.
        if not valider_requete(self.request, action="connexion"):
            raise ValidationError(MESSAGE_ECHEC)

        username = self.cleaned_data.get("username")
        password = self.cleaned_data.get("password")

        if username and "@" in username:
            matched_user = User.objects.filter(email__iexact=username).only("username").first()
            if matched_user:
                username = matched_user.username
                self.cleaned_data["username"] = username

        if username and password:
            self.user_cache = authenticate(self.request, username=username, password=password)
            if self.user_cache is None:
                raise self.get_invalid_login_error()
            self.confirm_login_allowed(self.user_cache)

        if not username or not password:
            raise ValidationError("Veuillez renseigner vos identifiants.")

        return self.cleaned_data


class ProfilForm(FormulaireModeleITEAG):
    """Coordonnées que chacun tient à jour lui-même.

    Le rôle, le statut et les droits n'y figurent pas : ils relèvent de
    l'administration. Un compte peut corriger son adresse, pas se promouvoir.
    """

    class Meta:
        model = User
        fields = [
            "first_name",
            "last_name",
            "email",
            "phone",
            "photo",
            "adresse",
            "complement_adresse",
            "code_postal",
            "ville",
            "pays",
        ]
        labels = {
            "first_name": "Prénom",
            "last_name": "Nom",
            "email": "Adresse électronique",
        }
        help_texts = {
            "email": "Sert à la connexion, aux notifications et à la réinitialisation du mot de passe.",
            "photo": "JPEG ou PNG, 2 Mo au plus.",
        }
        widgets = {
            "adresse": forms.TextInput(attrs={"autocomplete": "street-address"}),
            "code_postal": forms.TextInput(attrs={"autocomplete": "postal-code"}),
            "ville": forms.TextInput(attrs={"autocomplete": "address-level2"}),
            "phone": forms.TextInput(attrs={"autocomplete": "tel", "inputmode": "tel"}),
        }

    # L'identité d'un étudiant figure sur ses relevés, ses attestations et son
    # diplôme. La laisser modifiable par l'intéressé, c'est accepter qu'un
    # document officiel soit édité au nom que quelqu'un s'est choisi la veille.
    # Un changement d'état civil existe — il passe par le secrétariat, sur
    # pièce, comme dans n'importe quel établissement.
    IDENTITE = ("first_name", "last_name")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for nom in ("first_name", "last_name", "email"):
            self.fields[nom].required = True

        if self.identite_verrouillee:
            for nom in self.IDENTITE:
                champ = self.fields[nom]
                champ.disabled = True
                champ.help_text = "Modifiable par le secrétariat uniquement, sur présentation d'une pièce d'état civil."

    @property
    def identite_verrouillee(self) -> bool:
        """Vrai dès qu'un dossier de scolarité porte cette identité."""
        return hasattr(self.instance, "profil_etudiant")

    def clean_email(self):
        """Deux comptes ne peuvent pas partager une adresse : elle sert à se connecter."""
        email = self.cleaned_data["email"].strip()
        if User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
            raise ValidationError("Cette adresse est déjà utilisée par un autre compte.")
        return email

    def clean_photo(self):
        """Un portrait de 12 Mo ferait ramer chaque page où il s'affiche."""
        photo = self.cleaned_data.get("photo")
        taille = getattr(photo, "size", None)
        if taille is not None and taille > 2 * 1024 * 1024:
            raise ValidationError("Photo trop lourde : 2 Mo au plus.")
        return photo


class SignatureForm(FormulaireModeleITEAG):
    class Meta:
        model = User
        fields = ["signature"]
        help_texts = {
            "signature": "PNG transparent recommandé. JPEG ou WebP acceptés, 2 Mo au plus.",
        }

    def clean_signature(self):
        signature = self.cleaned_data.get("signature")
        taille = getattr(signature, "size", None)
        if taille is not None and taille > 2 * 1024 * 1024:
            raise ValidationError("Signature trop lourde : 2 Mo au plus.")

        image = getattr(signature, "image", None)
        format_image = getattr(image, "format", "")
        if format_image and format_image.upper() not in {"PNG", "JPEG", "WEBP"}:
            raise ValidationError("Format non accepté : utilisez une image PNG, JPEG ou WebP.")
        return signature


class MotDePasseForm(PasswordChangeForm):
    """Changement de mot de passe, habillé à la charte."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        habiller(self)
        self.fields["old_password"].label = "Mot de passe actuel"
        self.fields["new_password1"].label = "Nouveau mot de passe"
        self.fields["new_password2"].label = "Confirmation du nouveau mot de passe"
