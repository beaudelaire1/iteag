"""Formulaires liés aux pièces réclamées à un candidat."""

from django import forms

from apps.admissions.models import PieceDemandee
from apps.core.formulaires import FormulaireITEAG, FormulaireModeleITEAG

# Les justificatifs que l'ITEAG réclame le plus souvent. Les proposer en cases
# à cocher évite de les ressaisir à chaque dossier — et évite surtout les
# libellés qui varient d'un dossier à l'autre, qui rendent tout décompte faux.
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


class DemandePiecesForm(FormulaireITEAG):
    """Réclame une ou plusieurs pièces à un candidat, en une fois."""

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
        label="Précisions communes",
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="Ajoutées à chaque pièce réclamée. Le candidat les lit sur sa page de suivi.",
    )
    date_limite = forms.DateField(
        label="À fournir avant le",
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
        help_text="Facultatif. Une pièce en retard est signalée dans la liste des dossiers.",
    )

    def __init__(self, *args, dossier=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.dossier = dossier
        # Ne pas reproposer ce qui a déjà été réclamé : la contrainte d'unicité
        # le refuserait, et l'erreur serait incompréhensible pour l'utilisateur.
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
        """Toutes les pièces à créer, liste et champ libre confondus."""
        retenues = list(self.cleaned_data.get("pieces") or [])
        libre = (self.cleaned_data.get("piece_libre") or "").strip()
        if libre:
            retenues.append(libre)
        return retenues


class DepotPieceForm(FormulaireModeleITEAG):
    """Dépôt d'une pièce par le candidat, depuis sa page de suivi."""

    EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".doc", ".docx", ".odt"}
    TAILLE_MAX = 10 * 1024 * 1024

    class Meta:
        model = PieceDemandee
        fields = ["fichier"]
        widgets = {"fichier": forms.ClearableFileInput(attrs={"accept": ".pdf,.jpg,.jpeg,.png,.doc,.docx,.odt"})}

    def clean_fichier(self):
        fichier = self.cleaned_data.get("fichier")
        if not fichier:
            raise forms.ValidationError("Choisissez un fichier.")

        nom = fichier.name.lower()
        if not any(nom.endswith(extension) for extension in self.EXTENSIONS):
            raise forms.ValidationError("Formats acceptés : PDF, JPEG, PNG, Word ou OpenDocument.")
        if fichier.size > self.TAILLE_MAX:
            raise forms.ValidationError("Le fichier dépasse 10 Mo. Réduisez-le ou scannez en qualité inférieure.")
        return fichier
