"""Formulaires de production de contenu — portail enseignant."""

import hashlib

from django import forms
from django.conf import settings
from django.utils.text import slugify

from apps.elearning.models import Chapitre, Lecon, ModuleFormation, SousTitre, VideoAsset

INPUT = "form-input"
SELECT = "form-select"
FICHIER = "form-file"


class ModuleForm(forms.ModelForm):
    """Création et édition d'un module par son responsable."""

    class Meta:
        model = ModuleFormation
        fields = [
            "titre",
            "code",
            "description",
            "objectifs",
            "discipline",
            "cours",
            "niveau",
            "image_couverture",
            "ects",
            "certifiant",
            "seuil_completion",
            "autorise_revision",
        ]
        widgets = {
            "titre": forms.TextInput(attrs={"class": INPUT}),
            "code": forms.TextInput(attrs={"class": INPUT, "placeholder": "Ex. CHR-101"}),
            "description": forms.Textarea(attrs={"class": INPUT, "rows": 4}),
            "objectifs": forms.Textarea(attrs={"class": INPUT, "rows": 4}),
            "discipline": forms.Select(attrs={"class": SELECT}),
            "cours": forms.Select(attrs={"class": SELECT}),
            "niveau": forms.Select(attrs={"class": SELECT}),
            "image_couverture": forms.ClearableFileInput(attrs={"class": FICHIER}),
            "ects": forms.NumberInput(attrs={"class": INPUT, "min": 0, "step": "0.5"}),
            "seuil_completion": forms.NumberInput(attrs={"class": INPUT, "min": 50, "max": 100}),
        }
        help_texts = {
            "seuil_completion": "Part du module à visionner pour qu'il soit considéré comme terminé.",
            "certifiant": "Une attestation est émise automatiquement à la complétion.",
        }

    def save(self, commit=True):
        module = super().save(commit=False)
        if not module.slug:
            module.slug = self._slug_libre(module.titre)
        if commit:
            module.save()
            self.save_m2m()
        return module

    @staticmethod
    def _slug_libre(titre: str) -> str:
        base = slugify(titre)[:240] or "module"
        candidat, suffixe = base, 1
        while ModuleFormation.objects.filter(slug=candidat).exists():
            suffixe += 1
            candidat = f"{base}-{suffixe}"
        return candidat


class ChapitreForm(forms.ModelForm):
    class Meta:
        model = Chapitre
        fields = ["titre", "description", "ordre"]
        widgets = {
            "titre": forms.TextInput(attrs={"class": INPUT}),
            "description": forms.Textarea(attrs={"class": INPUT, "rows": 2}),
            "ordre": forms.NumberInput(attrs={"class": INPUT, "min": 0}),
        }


class LeconForm(forms.ModelForm):
    """Une leçon : vidéo, document, texte ou lien."""

    class Meta:
        model = Lecon
        fields = [
            "titre",
            "type_lecon",
            "ordre",
            "video",
            "document",
            "lien_externe",
            "contenu_texte",
            "duree_secondes",
            "apercu_gratuit",
            "obligatoire",
        ]
        widgets = {
            "titre": forms.TextInput(attrs={"class": INPUT}),
            "type_lecon": forms.Select(attrs={"class": SELECT}),
            "ordre": forms.NumberInput(attrs={"class": INPUT, "min": 0}),
            "video": forms.Select(attrs={"class": SELECT}),
            "document": forms.ClearableFileInput(attrs={"class": FICHIER}),
            "lien_externe": forms.URLInput(attrs={"class": INPUT}),
            "contenu_texte": forms.Textarea(attrs={"class": INPUT, "rows": 6}),
            "duree_secondes": forms.NumberInput(attrs={"class": INPUT, "min": 0}),
        }
        help_texts = {
            "apercu_gratuit": "Visible sans compte ni droit — sert de vitrine au module.",
            "obligatoire": "Compte dans le calcul de complétion du module.",
        }

    def __init__(self, *args, enseignant=None, **kwargs):
        super().__init__(*args, **kwargs)
        # Un enseignant ne rattache que ses propres vidéos.
        if enseignant is not None:
            self.fields["video"].queryset = VideoAsset.objects.filter(uploade_par=enseignant).order_by("-created_at")

    def clean(self):
        donnees = super().clean()
        type_lecon = donnees.get("type_lecon")
        if type_lecon == Lecon.TypeLecon.VIDEO and not donnees.get("video"):
            self.add_error("video", "Une leçon vidéo doit référencer un fichier déjà déposé.")
        if type_lecon == Lecon.TypeLecon.LIEN_EXTERNE and not donnees.get("lien_externe"):
            self.add_error("lien_externe", "Indiquez l'adresse de la ressource.")
        if type_lecon == Lecon.TypeLecon.DOCUMENT and not (donnees.get("document") or self.instance.document):
            self.add_error("document", "Joignez le document.")
        return donnees

    def save(self, commit=True):
        lecon = super().save(commit=False)
        if not lecon.slug:
            lecon.slug = slugify(lecon.titre)[:240] or "lecon"
        if commit:
            lecon.save()
        return lecon


class VideoUploadForm(forms.Form):
    """
    Dépôt d'un fichier vidéo.

    Le type réel est contrôlé à partir des premiers octets, pas de l'extension :
    renommer un exécutable en .mp4 ne doit pas suffire à le faire accepter.
    """

    titre = forms.CharField(
        label="Titre de la vidéo",
        max_length=250,
        widget=forms.TextInput(attrs={"class": INPUT}),
    )
    fichier = forms.FileField(
        label="Fichier vidéo",
        widget=forms.ClearableFileInput(attrs={"class": FICHIER, "accept": "video/*"}),
    )
    transcription = forms.CharField(
        label="Transcription (facultative)",
        required=False,
        widget=forms.Textarea(attrs={"class": INPUT, "rows": 5}),
        help_text="Améliore l'accessibilité et le référencement.",
    )

    # Signatures des conteneurs vidéo acceptés, lues en tête de fichier.
    SIGNATURES = {
        b"\x1aE\xdf\xa3": "video/webm",  # Matroska / WebM
    }
    MARQUEUR_MP4 = b"ftyp"  # présent à l'octet 4 des conteneurs ISO (MP4, MOV)

    def clean_fichier(self):
        fichier = self.cleaned_data["fichier"]

        taille_max = getattr(settings, "ELEARNING_TAILLE_VIDEO_MAX", 2 * 1024**3)
        if fichier.size > taille_max:
            raise forms.ValidationError(f"Fichier trop volumineux : maximum {taille_max // 1024**2} Mo.")

        entete = fichier.read(12)
        fichier.seek(0)
        if not self._entete_video(entete):
            raise forms.ValidationError("Ce fichier n'est pas une vidéo reconnue. Formats acceptés : MP4, MOV, WebM.")
        return fichier

    @classmethod
    def _entete_video(cls, entete: bytes) -> bool:
        if len(entete) < 12:
            return False
        if entete[4:8] == cls.MARQUEUR_MP4:
            return True
        return any(entete.startswith(signature) for signature in cls.SIGNATURES)

    @staticmethod
    def empreinte(fichier) -> str:
        """Empreinte SHA-256, calculée par blocs pour ne pas charger le fichier en mémoire."""
        condensat = hashlib.sha256()
        for bloc in fichier.chunks():
            condensat.update(bloc)
        fichier.seek(0)
        return condensat.hexdigest()


class SousTitreForm(forms.ModelForm):
    class Meta:
        model = SousTitre
        fields = ["langue", "libelle", "fichier_vtt", "par_defaut"]
        widgets = {
            "langue": forms.TextInput(attrs={"class": INPUT, "placeholder": "fr"}),
            "libelle": forms.TextInput(attrs={"class": INPUT, "placeholder": "Français"}),
            "fichier_vtt": forms.ClearableFileInput(attrs={"class": FICHIER, "accept": ".vtt"}),
        }

    def clean_fichier_vtt(self):
        fichier = self.cleaned_data["fichier_vtt"]
        entete = fichier.read(6)
        fichier.seek(0)
        if not entete.startswith(b"WEBVTT"):
            raise forms.ValidationError("Le fichier doit être au format WebVTT (il commence par « WEBVTT »).")
        return fichier
