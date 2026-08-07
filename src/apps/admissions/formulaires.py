"""Formulaires liés aux pièces réclamées à un candidat."""

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


def valider_fichier_piece(fichier):
    if not fichier:
        raise forms.ValidationError("Choisissez un fichier.")
    nom = fichier.name.lower()
    if not any(nom.endswith(extension) for extension in EXTENSIONS_PIECES):
        raise forms.ValidationError("Formats acceptés : PDF, JPEG, PNG, Word ou OpenDocument.")
    if fichier.size > TAILLE_MAX_PIECE:
        raise forms.ValidationError("Le fichier dépasse 10 Mo. Réduisez-le ou scannez en qualité inférieure.")
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
