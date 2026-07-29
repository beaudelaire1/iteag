"""Formulaires de production de contenu — portail enseignant."""

import re
from decimal import Decimal
from urllib.parse import parse_qs, urlparse

from django import forms
from django.conf import settings
from django.utils.text import slugify

from apps.core.formulaires import FormulaireITEAG, FormulaireModeleITEAG
from apps.elearning.diffusion import fournisseur_compatible
from apps.elearning.models import Chapitre, Lecon, ModuleFormation, RessourceLecon, SousTitre, VideoAsset

INPUT = "form-input"
SELECT = "form-select"
FICHIER = "form-file"


class ModuleForm(FormulaireModeleITEAG):
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
            # Le responsable décidait de tout sauf de qui peut voir son module :
            # la politique restait invisible, subie, et jamais confrontée aux
            # aperçus qu'il cochait par ailleurs.
            "politique_acces",
            "prix_ttc",
            "taux_tva",
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
            "politique_acces": forms.Select(attrs={"class": SELECT}),
            "prix_ttc": forms.NumberInput(attrs={"class": INPUT, "min": 0, "step": "0.01"}),
            "taux_tva": forms.NumberInput(attrs={"class": INPUT, "min": 0, "max": 100, "step": "0.01"}),
            "seuil_completion": forms.NumberInput(attrs={"class": INPUT, "min": 50, "max": 100}),
        }
        help_texts = {
            "seuil_completion": "Part du module à visionner pour qu'il soit considéré comme terminé.",
            "certifiant": "Une attestation est émise automatiquement à la complétion.",
            "politique_acces": (
                "Qui peut consulter les leçons. « Public » ouvre le module à tous les visiteurs ; "
                "les autres exigent un droit, que le secrétariat octroie. Une leçon cochée "
                "« aperçu gratuit » échappe à ce choix, quelle que soit la politique retenue."
            ),
            "prix_ttc": "Prix payé par l'étudiant, toutes taxes comprises. L'accès acheté est définitif.",
            "taux_tva": "Appliqué à ce module seul. 0 en cas d'exonération de formation professionnelle.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Le champ n'est pas obligatoire, mais son absence ne vaut jamais
        # « ouvert » : `clean_politique_acces` retombe sur la valeur en place,
        # à défaut sur le défaut du modèle, qui est le plus fermé.
        self.fields["politique_acces"].required = False
        self.fields["prix_ttc"].required = False
        self.fields["taux_tva"].required = False
        if self.instance.pk is None:
            self.fields["taux_tva"].initial = getattr(settings, "PAIEMENTS_TAUX_TVA_DEFAUT", "0.00")

    def clean_prix_ttc(self):
        return self.cleaned_data.get("prix_ttc") or Decimal("0")

    def clean_taux_tva(self):
        return self.cleaned_data.get("taux_tva") or Decimal("0")

    def clean(self):
        donnees = super().clean()
        # Annoncer un module « vendu à l'unité » sans prix produirait un bouton
        # d'achat à zéro euro : l'accès s'ouvrirait pour rien.
        if donnees.get("politique_acces") == ModuleFormation.PolitiqueAcces.ACHAT and not donnees.get("prix_ttc"):
            self.add_error("prix_ttc", "Un module vendu à l'unité doit porter un prix.")
        return donnees

    def clean_politique_acces(self):
        """Resserrer la politique ne doit pas rendre le module inlisible.

        Le modèle vérifie déjà qu'une leçon n'est pas servie par un fournisseur
        trop faible pour son module (ADR-005) — mais il le vérifie du côté de la
        leçon. Rien n'empêchait de resserrer la politique *après* coup : les
        leçons devenaient incompatibles sans que personne ne l'apprenne avant la
        prochaine tentative de publication.
        """
        politique = self.cleaned_data.get("politique_acces") or self.instance.politique_acces
        if self.instance.pk is None:
            return politique

        incompatibles = [
            lecon
            for lecon in self.instance.lecons()
            if lecon.video is not None
            and not lecon.apercu_gratuit
            and not fournisseur_compatible(lecon.video.fournisseur, politique)
        ]
        if incompatibles:
            noms = ", ".join(f"« {lecon.titre} »" for lecon in incompatibles[:3])
            reste = len(incompatibles) - 3
            if reste > 0:
                noms += f" et {reste} autre{'s' if reste > 1 else ''}"
            raise forms.ValidationError(
                f"{noms} : ces leçons sont hébergées chez un fournisseur qui ne sait pas retirer "
                "un accès déjà délivré. Remplacez leur vidéo par une source à adresse signée "
                "avant de resserrer la politique."
            )
        return politique

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


class ChapitreForm(FormulaireModeleITEAG):
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


class LeconForm(FormulaireModeleITEAG):
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


class RessourceLeconForm(FormulaireModeleITEAG):
    """
    Dépôt d'un support pédagogique sur une leçon.

    Contrairement aux vidéos, ces fichiers transitent par le serveur : la
    liste des formats est donc fermée — des supports de cours, pas des
    exécutables — et la taille plafonnée pour qu'un dépôt ne monopolise pas
    le serveur d'application.
    """

    EXTENSIONS_AUTORISEES = {
        "pdf",
        "doc",
        "docx",
        "ppt",
        "pptx",
        "xls",
        "xlsx",
        "odt",
        "odp",
        "ods",
        "rtf",
        "txt",
        "md",
        "csv",
        "jpg",
        "jpeg",
        "png",
        "webp",
        "zip",
        "epub",
        "mp3",
    }
    TAILLE_MAX_OCTETS = 50 * 1024 * 1024

    class Meta:
        model = RessourceLecon
        fields = ["titre", "fichier", "lien_externe"]
        widgets = {
            "titre": forms.TextInput(attrs={"class": INPUT, "placeholder": "Ex. Notes de cours (PDF)"}),
            "fichier": forms.ClearableFileInput(attrs={"class": FICHIER}),
            "lien_externe": forms.URLInput(attrs={"class": INPUT, "placeholder": "https://…"}),
        }
        help_texts = {
            "fichier": "PDF, bureautique, image, archive ZIP ou audio MP3 — 50 Mo au plus.",
            "lien_externe": "À défaut de fichier : adresse HTTPS d'une ressource externe.",
        }

    def clean_fichier(self):
        fichier = self.cleaned_data.get("fichier")
        if not fichier:
            return fichier
        extension = (fichier.name.rsplit(".", 1)[-1] if "." in fichier.name else "").lower()
        if extension not in self.EXTENSIONS_AUTORISEES:
            raise forms.ValidationError(
                f"Le format « .{extension or '?'} » n'est pas accepté. Formats possibles : "
                + ", ".join(sorted(self.EXTENSIONS_AUTORISEES))
                + "."
            )
        if fichier.size > self.TAILLE_MAX_OCTETS:
            raise forms.ValidationError("Le fichier dépasse 50 Mo. Déposez-le chez un hébergeur et donnez le lien.")
        return fichier

    def clean_lien_externe(self):
        lien = self.cleaned_data.get("lien_externe", "").strip()
        if lien and not lien.startswith("https://"):
            raise forms.ValidationError("Le lien doit utiliser HTTPS.")
        return lien

    def clean(self):
        donnees = super().clean()
        fichier = donnees.get("fichier") or self.instance.fichier
        lien = donnees.get("lien_externe")
        if fichier and lien:
            self.add_error("lien_externe", "Choisissez : un fichier ou un lien, pas les deux.")
        if not fichier and not lien:
            self.add_error("fichier", "Joignez un fichier, ou indiquez un lien externe.")
        return donnees


class SousTitreForm(FormulaireModeleITEAG):
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


class VideoExterneForm(FormulaireITEAG):
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
