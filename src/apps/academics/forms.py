from django import forms

from apps.academics.models import DemandeInscriptionCours
from apps.core.formulaires import FormulaireModeleITEAG
from apps.core.validation_fichiers import RegleFichier, valider_fichier
from apps.lms.models import Evaluation

# Ces deux règles emploient le contrôle de `apps.core.validation_fichiers` —
# extension, type annoncé, signature binaire, et structure de l'archive pour
# les formats bureautiques ZIP. Elles ne contrôlaient auparavant qu'extension
# et taille, alors que la candidature vérifiait déjà le contenu réel : un
# fichier HTML renommé en `.pdf` était refusé d'un côté, accepté de l'autre.
REGLE_COPIE = RegleFichier(
    extensions=frozenset({".pdf", ".doc", ".docx", ".odt"}),
    taille_max=10 * 1024 * 1024,
    message_formats="Formats acceptés : PDF, DOC, DOCX ou ODT.",
)
REGLE_JUSTIFICATIF_PAIEMENT = RegleFichier(
    extensions=frozenset({".pdf", ".jpg", ".jpeg", ".png"}),
    taille_max=5 * 1024 * 1024,
    message_formats="Formats acceptés : PDF, JPG ou PNG.",
)


class StudentSubmissionForm(FormulaireModeleITEAG):
    class Meta:
        model = Evaluation
        fields = ["fichier_soumis"]
        widgets = {
            "fichier_soumis": forms.ClearableFileInput(attrs={"class": "form-file", "accept": REGLE_COPIE.accept})
        }

    def clean_fichier_soumis(self):
        uploaded = self.cleaned_data.get("fichier_soumis")
        if not uploaded:
            raise forms.ValidationError("Sélectionnez le fichier à remettre.")
        return valider_fichier(uploaded, REGLE_COPIE)


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
