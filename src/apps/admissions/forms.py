from django import forms
from django.core.exceptions import ValidationError

from apps.core.formulaires import FormulaireModeleITEAG

from .formulaires import ACCEPT_PIECES, REGLE_PIECES, TAILLE_MAX_PIECE, valider_fichier_piece
from .models import DossierCandidature


class CandidatureForm(FormulaireModeleITEAG):
    """Formulaire public multi-étapes de candidature — PUB-011."""

    # Honeypot anti-spam : champ invisible pour les humains
    honeypot = forms.CharField(required=False, widget=forms.HiddenInput())

    class Meta:
        model = DossierCandidature
        fields = [
            "nom",
            "prenom",
            "email",
            "telephone",
            "date_naissance",
            "parcours_souhaite",
            "motivations",
            "eglise",
            "eglise_fondatrice",
            "piece_identite",
            "diplomes",
            "autre_document",
        ]
        widgets = {
            "motivations": forms.Textarea(attrs={"rows": 5}),
            "date_naissance": forms.DateInput(attrs={"type": "date"}),
        }

    # Le dossier passe par trois moments distincts : qui vous êtes, ce que vous
    # visez, ce que vous joignez. Les présenter d'affilée dans une seule colonne
    # ne dit pas où l'on en est ; les regrouper le dit sans un mot de plus.
    SECTIONS = (
        {
            "titre": "Votre identité",
            "aide": "",
            "noms": ("nom", "prenom", "email", "telephone", "date_naissance"),
        },
        {
            "titre": "Votre projet",
            "aide": "",
            "noms": ("parcours_souhaite", "motivations", "eglise", "eglise_fondatrice"),
        },
        {
            "titre": "Vos pièces justificatives",
            "aide": (
                "Trois documents au plus, facultatifs à ce stade : le secrétariat "
                "vous réclamera ce qui manque après examen du dossier."
            ),
            "noms": ("piece_identite", "diplomes", "autre_document"),
        },
    )

    AIDES = {
        "eglise": "Le nom de votre assemblée, par exemple « Église Protestante Évangélique de Morne Bernard ».",
        "piece_identite": "Carte d'identité, passeport ou titre de séjour, recto-verso.",
        "diplomes": "Vos derniers diplômes ou relevés de notes, en un seul document si possible.",
        "autre_document": "Lettre de recommandation, curriculum vitæ, ou toute pièce utile à votre dossier.",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Les trois fichiers du dépôt initial sont des justificatifs au même
        # titre que ceux réclamés plus tard par le secrétariat. Ils appliquent
        # donc exactement le même contrat de format, taille et signature.
        for nom in ("piece_identite", "diplomes", "autre_document"):
            champ = self.fields[nom]
            champ.validators.append(valider_fichier_piece)
            champ.widget.attrs["accept"] = ACCEPT_PIECES

        # Le contrat de dépôt ne se devine pas : sans lui, on découvre le
        # format refusé et le poids maximal en essuyant une erreur.
        formats = f"{REGLE_PIECES.message_formats} {TAILLE_MAX_PIECE // (1024 * 1024)} Mo maximum."
        for nom, aide in self.AIDES.items():
            champ = self.fields[nom]
            champ.help_text = f"{aide} {formats}" if nom != "eglise" else aide

        # « --------- » n'est pas un intitulé : il n'indique ni qu'un choix est
        # attendu, ni ce qu'on choisit.
        self.fields["parcours_souhaite"].empty_label = "Choisissez un parcours"

    def sections(self):
        """Les champs visibles, groupés — l'ordre et le contenu viennent d'ici."""
        for section in self.SECTIONS:
            yield {
                "titre": section["titre"],
                "aide": section["aide"],
                "champs": [self[nom] for nom in section["noms"]],
            }

    def clean_honeypot(self):
        if self.cleaned_data.get("honeypot"):
            raise ValidationError("Soumission rejetée.")
        return ""
