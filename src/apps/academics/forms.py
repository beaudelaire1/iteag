from django import forms

from apps.academics.models import DemandeInscriptionCours
from apps.core.formulaires import FormulaireModeleITEAG
from apps.core.validation_fichiers import RegleFichier, valider_fichier

REGLE_JUSTIFICATIF_PAIEMENT = RegleFichier(
    extensions=frozenset({".pdf", ".jpg", ".jpeg", ".png"}),
    taille_max=5 * 1024 * 1024,
    message_formats="Formats acceptés : PDF, JPG ou PNG.",
)


class EnrollmentRequestForm(FormulaireModeleITEAG):
    class Meta:
        model = DemandeInscriptionCours
        fields = ["note_etudiant", "reference_paiement", "justificatif_paiement"]
        widgets = {
            "note_etudiant": forms.Textarea(
                attrs={
                    "class": "form-input",
                    "rows": 4,
                    "placeholder": "Précisez si nécessaire votre objectif ou une contrainte particulière.",
                }
            ),
            "reference_paiement": forms.TextInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "Référence de virement ou de reçu, si le règlement est déjà effectué",
                }
            ),
            "justificatif_paiement": forms.ClearableFileInput(
                attrs={"class": "form-file", "accept": REGLE_JUSTIFICATIF_PAIEMENT.accept}
            ),
        }

    def clean_justificatif_paiement(self):
        uploaded = self.cleaned_data.get("justificatif_paiement")
        if not uploaded:
            return uploaded
        return valider_fichier(uploaded, REGLE_JUSTIFICATIF_PAIEMENT)
