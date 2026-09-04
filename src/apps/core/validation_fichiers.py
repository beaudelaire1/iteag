"""
Le contrôle des fichiers déposés, en un seul endroit.

Une extension ne prouve rien : `virus.html` renommé `justificatif.pdf` passe
tous les contrôles de nom. Ce qui tranche, c'est la signature binaire — et,
pour les formats bureautiques ZIP, la structure interne de l'archive, car DOCX
et ODT partagent leur en-tête avec des dizaines de formats sans rapport.

Ce module a été extrait de `apps/admissions/formulaires.py`, où il ne servait
qu'aux candidatures. La remise de devoir, elle, ne contrôlait qu'extension et
taille : la même classe de fichier recevait donc deux réponses différentes
selon la porte par laquelle elle entrait. Le risque immédiat était faible ; le
vrai coût était la double règle, qui dérive dès qu'un format s'ajoute d'un
côté seulement.

Chaque point d'entrée déclare désormais sa `RegleFichier` — les formats qu'il
accepte et sa taille limite — et le contrôle, lui, est le même pour tous.
"""

from dataclasses import dataclass
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from django import forms

# Ce que l'on sait des formats, indépendamment de qui les reçoit.
MIMES_CONNUS = {
    ".pdf": {"application/pdf"},
    ".jpg": {"image/jpeg"},
    ".jpeg": {"image/jpeg"},
    ".png": {"image/png"},
    ".doc": {"application/msword", "application/vnd.ms-office"},
    ".docx": {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/zip",
    },
    ".odt": {"application/vnd.oasis.opendocument.text", "application/zip"},
    # Vidéo. Deux familles de conteneurs seulement : ISO Base Media, qui porte
    # « ftyp » au cinquième octet, et EBML, reconnaissable dès le premier.
    ".mp4": {"video/mp4"},
    ".m4v": {"video/x-m4v", "video/mp4"},
    ".mov": {"video/quicktime", "video/mp4"},
    ".webm": {"video/webm"},
    ".mkv": {"video/x-matroska", "video/webm"},
}
CONTENEURS_ISO_BMFF = {".mp4", ".m4v", ".mov"}
CONTENEURS_EBML = {".webm", ".mkv"}
# Certains navigateurs et clients mobiles n'annoncent aucun type utile. Refuser
# sur cette seule base rejetterait des dépôts parfaitement valides : c'est la
# signature binaire qui tranche ensuite.
MIMES_GENERIQUES = {"", "application/octet-stream", "binary/octet-stream"}


@dataclass(frozen=True)
class RegleFichier:
    """Ce qu'un point de dépôt donné accepte."""

    extensions: frozenset[str]
    taille_max: int
    message_formats: str

    @property
    def accept(self) -> str:
        """Valeur de l'attribut HTML `accept`, dans un ordre stable."""
        return ",".join(sorted(self.extensions))

    @property
    def taille_max_lisible(self) -> str:
        return f"{self.taille_max // (1024 * 1024)} Mo"

    def __post_init__(self):
        inconnues = set(self.extensions) - set(MIMES_CONNUS)
        if inconnues:
            # Une extension sans signature connue passerait le contrôle sans
            # être vérifiée : mieux vaut le refus au démarrage que le faux
            # sentiment de sécurité à l'exécution.
            raise ValueError(
                f"Aucune signature binaire n'est connue pour {sorted(inconnues)} : "
                "ajoutez-la à MIMES_CONNUS et à _signature_valide avant de l'accepter."
            )


def _position_fichier(fichier):
    try:
        return fichier.tell()
    except (AttributeError, OSError):
        return None


def _revenir(fichier, position) -> bool:
    try:
        fichier.seek(0 if position is None else position)
    except (AttributeError, OSError):
        return False
    return True


def _entete(fichier, taille=16) -> bytes:
    position = _position_fichier(fichier)
    try:
        fichier.seek(0)
        return fichier.read(taille)
    except (AttributeError, OSError):
        return b""
    finally:
        _revenir(fichier, position)


def _zip_valide(fichier, extension: str) -> bool:
    """Valide la structure minimale des formats bureautiques ZIP.

    DOCX et ODT partagent la signature ZIP avec de nombreux formats sans rapport.
    Ouvrir seulement le répertoire central et un minuscule fichier de métadonnées
    permet de les distinguer sans extraire le contenu ni exécuter quoi que ce soit.
    """

    position = _position_fichier(fichier)
    try:
        fichier.seek(0)
        with ZipFile(fichier) as archive:
            noms = set(archive.namelist())
            if extension == ".docx":
                return "[Content_Types].xml" in noms and any(nom.startswith("word/") for nom in noms)
            if extension == ".odt":
                if "mimetype" not in noms:
                    return False
                return archive.read("mimetype", pwd=None) == b"application/vnd.oasis.opendocument.text"
            return False
    except (AttributeError, OSError, BadZipFile, KeyError, RuntimeError):
        return False
    finally:
        _revenir(fichier, position)


def _signature_valide(fichier, extension: str) -> bool:
    entete = _entete(fichier)
    if extension == ".pdf":
        return entete.startswith(b"%PDF-")
    if extension in {".jpg", ".jpeg"}:
        return entete.startswith(b"\xff\xd8\xff")
    if extension == ".png":
        return entete.startswith(b"\x89PNG\r\n\x1a\n")
    if extension == ".doc":
        return entete.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1")
    if extension in {".docx", ".odt"}:
        return entete.startswith(b"PK\x03\x04") and _zip_valide(fichier, extension)
    if extension in CONTENEURS_ISO_BMFF:
        # La taille de la première boîte précède le type : « ftyp » se lit donc
        # au cinquième octet, jamais au premier.
        return entete[4:8] == b"ftyp"
    if extension in CONTENEURS_EBML:
        return entete.startswith(b"\x1a\x45\xdf\xa3")
    return False


def valider_fichier(fichier, regle: RegleFichier):
    """Refuse un fichier dont le nom ne correspond pas au contenu réel."""

    if not fichier:
        raise forms.ValidationError("Choisissez un fichier.")

    extension = Path(fichier.name).suffix.lower()
    if extension not in regle.extensions:
        raise forms.ValidationError(regle.message_formats)
    if fichier.size > regle.taille_max:
        raise forms.ValidationError(
            f"Le fichier dépasse {regle.taille_max_lisible}. Réduisez-le ou scannez en qualité inférieure."
        )
    if fichier.size <= 0:
        raise forms.ValidationError("Le fichier est vide.")

    mime = (getattr(fichier, "content_type", "") or "").lower().split(";", 1)[0].strip()
    if mime not in MIMES_GENERIQUES and mime not in MIMES_CONNUS[extension]:
        raise forms.ValidationError("Le type du fichier ne correspond pas au format annoncé.")

    if not _signature_valide(fichier, extension):
        raise forms.ValidationError("Le contenu du fichier ne correspond pas à son extension.")

    # Les validateurs ne doivent pas laisser le curseur au milieu du fichier :
    # le stockage qui suit doit recevoir l'intégralité des octets.
    if not _revenir(fichier, 0):
        raise forms.ValidationError("Le fichier ne peut pas être lu de manière fiable.")
    return fichier
