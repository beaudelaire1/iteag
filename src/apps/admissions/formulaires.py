"""Formulaires liés aux pièces réclamées à un candidat."""

from pathlib import Path
from zipfile import BadZipFile, ZipFile

from django import forms

from apps.admissions.models import PieceDemandee
from apps.core.formulaires import FormulaireITEAG, FormulaireModeleITEAG

PIECES_COURANTES = [
    ("Acte de naissance", "Copie intégrale de moins de trois mois."),
    ("Copie du dernier diplôme", "Diplôme le plus élevé obtenu, avec relevé de notes si disponible."),
    ("Photo d'identité", "Format identité, sur fond clair, au format JPEG ou PNG."),
    ("Justificatif de domicile", "De moins de trois mois : facture, quittance ou attestation."),
    ("Lettre de recommandation pastorale", "Rédigée par le responsable de votre Église locale."),
    ("Copie de la pièce d'identité", "Carte nationale d'identité ou passeport en cours de validité."),
    ("Curriculum vitæ", "Parcours de formation et expérience de service."),
    ("Relevé d'identité bancaire", "Nécessaire pour la mise en place du prélèvement des frais."),
]

EXTENSIONS_PIECES = {".pdf", ".jpg", ".jpeg", ".png", ".doc", ".docx", ".odt"}
TAILLE_MAX_PIECE = 10 * 1024 * 1024
ACCEPT_PIECES = ".pdf,.jpg,.jpeg,.png,.doc,.docx,.odt"

MIMES_PIECES = {
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
}
MIMES_GENERIQUES = {"", "application/octet-stream", "binary/octet-stream"}


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
    return False


def valider_fichier_piece(fichier):
    """Refuse un justificatif dont le nom ne correspond pas au contenu réel."""

    if not fichier:
        raise forms.ValidationError("Choisissez un fichier.")

    extension = Path(fichier.name).suffix.lower()
    if extension not in EXTENSIONS_PIECES:
        raise forms.ValidationError("Formats acceptés : PDF, JPEG, PNG, Word ou OpenDocument.")
    if fichier.size > TAILLE_MAX_PIECE:
        raise forms.ValidationError("Le fichier dépasse 10 Mo. Réduisez-le ou scannez en qualité inférieure.")
    if fichier.size <= 0:
        raise forms.ValidationError("Le fichier est vide.")

    mime = (getattr(fichier, "content_type", "") or "").lower().split(";", 1)[0].strip()
    if mime not in MIMES_GENERIQUES and mime not in MIMES_PIECES[extension]:
        raise forms.ValidationError("Le type du fichier ne correspond pas au format annoncé.")

    if not _signature_valide(fichier, extension):
        raise forms.ValidationError("Le contenu du fichier ne correspond pas à son extension.")

    # Les validateurs ne doivent pas laisser le curseur au milieu du fichier :
    # le stockage qui suit doit recevoir l'intégralité des octets.
    if not _revenir(fichier, 0):
        raise forms.ValidationError("Le fichier ne peut pas être lu de manière fiable.")
    return fichier


class DemandePiecesForm(FormulaireITEAG):
    """Réclame plusieurs justificatifs comme une seule demande."""

    pieces = forms.MultipleChoiceField(
        label="Pièces à réclamer",
        choices=[(libelle, libelle) for libelle, _ in PIECES_COURANTES],
        widget=forms.CheckboxSelectMultiple,
        required=False,
    )
    piece_libre = forms.CharField(
        label="Autre pièce",
        max_length=150,
        required=False,
        help_text="Pour un justificatif qui ne figure pas dans la liste.",
    )
    precisions = forms.CharField(
        label="Message commun au candidat",
        required=False,
        widget=forms.Textarea(attrs={"rows": 4}),
        help_text=(
            "Ce texte est affiché et envoyé une seule fois pour l'ensemble de la demande. "
            "Les exigences propres à chaque document restent indiquées sous son libellé."
        ),
    )
    date_limite = forms.DateField(
        label="À fournir avant le",
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
        help_text="Facultatif. La même échéance s'applique à tout le lot.",
    )

    def __init__(self, *args, dossier=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.dossier = dossier
        if dossier is not None:
            deja = set(dossier.pieces_demandees.values_list("libelle", flat=True))
            self.fields["pieces"].choices = [
                (libelle, libelle) for libelle, _ in PIECES_COURANTES if libelle not in deja
            ]

    def clean(self):
        donnees = super().clean()
        choisies = donnees.get("pieces") or []
        libre = (donnees.get("piece_libre") or "").strip()
        if not choisies and not libre:
            raise forms.ValidationError("Sélectionnez au moins une pièce, ou saisissez-en une.")
        if libre and self.dossier is not None:
            if self.dossier.pieces_demandees.filter(libelle__iexact=libre).exists():
                self.add_error("piece_libre", "Cette pièce a déjà été réclamée à ce candidat.")
        return donnees

    def libelles(self) -> list[str]:
        retenues = list(self.cleaned_data.get("pieces") or [])
        libre = (self.cleaned_data.get("piece_libre") or "").strip()
        if libre:
            retenues.append(libre)
        return retenues


class DepotPiecesGroupeForm(FormulaireITEAG):
    """Un seul envoi pour tous les documents encore attendus d'une demande."""

    def __init__(self, *args, demande, **kwargs):
        super().__init__(*args, **kwargs)
        self.demande = demande
        self.pieces_attendues = [
            piece
            for piece in demande.pieces.all()
            if piece.statut in (PieceDemandee.Statut.DEMANDEE, PieceDemandee.Statut.REFUSEE)
        ]
        for piece in self.pieces_attendues:
            self.fields[f"piece_{piece.pk}"] = forms.FileField(
                label=piece.libelle,
                required=piece.obligatoire,
                validators=[valider_fichier_piece],
                widget=forms.ClearableFileInput(attrs={"accept": ACCEPT_PIECES, "class": "form-file"}),
                help_text=piece.precisions,
            )

    def fichiers(self):
        return [
            (piece, self.cleaned_data.get(f"piece_{piece.pk}"))
            for piece in self.pieces_attendues
            if self.cleaned_data.get(f"piece_{piece.pk}")
        ]


class DepotPieceForm(FormulaireModeleITEAG):
    """Compatibilité avec les anciennes demandes non regroupées."""

    class Meta:
        model = PieceDemandee
        fields = ["fichier"]
        widgets = {"fichier": forms.ClearableFileInput(attrs={"accept": ACCEPT_PIECES})}

    def clean_fichier(self):
        return valider_fichier_piece(self.cleaned_data.get("fichier"))
