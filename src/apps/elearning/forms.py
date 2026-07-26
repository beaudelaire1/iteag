"""Formulaires de production de contenu — portail enseignant."""

import re
from urllib.parse import parse_qs, urlparse

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
        help_texts = {"ordre": "Laisser 0 pour placer automatiquement le chapitre à la fin."}

    def __init__(self, *args, module=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.module = module

    def clean_ordre(self):
        ordre = self.cleaned_data["ordre"]
        if (
            ordre
            and self.module is not None
            and self.module.chapitres.filter(ordre=ordre).exclude(pk=self.instance.pk).exists()
        ):
            raise forms.ValidationError("Cette position est déjà utilisée dans le module.")
        return ordre


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
            "ordre": "Laisser 0 pour placer automatiquement la leçon à la fin.",
            "apercu_gratuit": "Visible sans compte ni droit — sert de vitrine au module.",
            "obligatoire": "Compte dans le calcul de complétion du module.",
        }

    def __init__(self, *args, enseignant=None, chapitre=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.chapitre = chapitre
        self.fields["duree_secondes"].required = False
        # Un enseignant ne rattache que ses propres vidéos.
        if enseignant is not None:
            self.fields["video"].queryset = VideoAsset.objects.filter(uploade_par=enseignant).order_by("-created_at")

    def clean_ordre(self):
        ordre = self.cleaned_data["ordre"]
        if (
            ordre
            and self.chapitre is not None
            and self.chapitre.lecons.filter(ordre=ordre).exclude(pk=self.instance.pk).exists()
        ):
            raise forms.ValidationError("Cette position est déjà utilisée dans le chapitre.")
        return ordre

    def clean_duree_secondes(self):
        return self.cleaned_data.get("duree_secondes") or 0

    def clean(self):
        donnees = super().clean()
        type_lecon = donnees.get("type_lecon")
        if type_lecon == Lecon.TypeLecon.VIDEO and not donnees.get("video"):
            self.add_error("video", "Une leçon vidéo doit référencer un lien vidéo déjà enregistré.")
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


class VideoExterneForm(forms.Form):
    """
    Référencement d'une vidéo déjà déposée chez le fournisseur.

    L'enseignant colle une adresse HTTPS. Le fournisseur et l'identifiant sont
    déduits de cette adresse puis validés avant l'enregistrement. Le média ne
    transite jamais par le serveur de l'institut.
    """

    titre = forms.CharField(
        label="Titre de la vidéo",
        max_length=250,
        widget=forms.TextInput(attrs={"class": INPUT}),
    )
    adresse_video = forms.URLField(
        label="Lien HTTPS de la vidéo",
        max_length=500,
        widget=forms.URLInput(
            attrs={
                "class": INPUT,
                "placeholder": "https://www.youtube.com/watch?v=…",
                "inputmode": "url",
            }
        ),
        help_text="Lien Bunny Stream, Vimeo ou YouTube. Aucun fichier n'est chargé sur le site.",
    )
    duree_secondes = forms.IntegerField(
        label="Durée (secondes)",
        min_value=0,
        required=False,
        widget=forms.NumberInput(attrs={"class": INPUT}),
        help_text="Renseignée par le fournisseur ; laisser vide si inconnue.",
    )
    transcription = forms.CharField(
        label="Transcription (facultative)",
        required=False,
        widget=forms.Textarea(attrs={"class": INPUT, "rows": 5}),
        help_text="Améliore l'accessibilité et le référencement.",
    )

    MOTIFS_IDENTIFIANT = {
        "bunny": re.compile(r"^[A-Za-z0-9_-]{6,64}$"),
        "youtube": re.compile(r"^[A-Za-z0-9_-]{11}$"),
        "vimeo": re.compile(r"^[0-9]{6,15}$"),
    }
    DOMAINES = {
        "youtube": ("youtube.com", "youtube-nocookie.com", "youtu.be"),
        "vimeo": ("vimeo.com",),
        "bunny": ("mediadelivery.net", "bunnycdn.com", "b-cdn.net"),
    }

    def clean_adresse_video(self):
        adresse = self.cleaned_data["adresse_video"].strip()
        analyse = urlparse(adresse)
        if analyse.scheme != "https":
            raise forms.ValidationError("Le lien doit utiliser HTTPS.")

        hote = (analyse.hostname or "").lower().rstrip(".")
        fournisseur = self._detecter_fournisseur(hote)
        if fournisseur is None:
            raise forms.ValidationError("Fournisseur non reconnu. Utiliser un lien Bunny Stream, Vimeo ou YouTube.")

        if fournisseur == "bunny" and (
            not getattr(settings, "BUNNY_ZONE_DIFFUSION", "") or not getattr(settings, "BUNNY_CLE_SIGNATURE", "")
        ):
            raise forms.ValidationError(
                "Bunny Stream n'est pas encore configuré. Renseigner la zone de diffusion et la clé de signature."
            )

        identifiant = self._extraire(analyse, fournisseur)
        if not self.MOTIFS_IDENTIFIANT[fournisseur].fullmatch(identifiant):
            raise forms.ValidationError("Le lien ne contient pas un identifiant vidéo valide.")
        if VideoAsset.objects.filter(cle_stockage=identifiant).exists():
            raise forms.ValidationError("Cette vidéo est déjà référencée.")

        self.fournisseur_detecte = fournisseur
        self.identifiant_detecte = identifiant
        return adresse

    def clean(self):
        donnees = super().clean()
        if hasattr(self, "fournisseur_detecte"):
            donnees["fournisseur"] = self.fournisseur_detecte
            donnees["identifiant"] = self.identifiant_detecte
        return donnees

    @classmethod
    def _detecter_fournisseur(cls, hote: str) -> str | None:
        zone_bunny = urlparse(getattr(settings, "BUNNY_ZONE_DIFFUSION", "")).hostname
        if zone_bunny and hote == zone_bunny.lower().rstrip("."):
            return "bunny"
        for fournisseur, domaines in cls.DOMAINES.items():
            if any(hote == domaine or hote.endswith(f".{domaine}") for domaine in domaines):
                return fournisseur
        return None

    @staticmethod
    def _extraire(analyse, fournisseur: str) -> str:
        parametres = parse_qs(analyse.query)
        if fournisseur == "youtube" and "v" in parametres:
            return parametres["v"][0]
        segments = [segment for segment in analyse.path.split("/") if segment]
        if (
            fournisseur == "bunny"
            and segments
            and segments[-1].lower()
            in {
                "playlist.m3u8",
                "master.m3u8",
            }
        ):
            segments.pop()
        return segments[-1] if segments else ""
