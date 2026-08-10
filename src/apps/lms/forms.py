from django import forms

from apps.academics.models import CoursDeSession
from apps.core.editeur_riche import ChampTexteRiche
from apps.core.formulaires import FormulaireITEAG, FormulaireModeleITEAG
from apps.core.validation_fichiers import RegleFichier, valider_fichier

from .models import Annonce, Choix, Devoir, Evaluation, GroupeEtudiants, Question, RessourcePedagogique

# Classes du système de design ITEAG (assets/css/input.css).
# Les formulaires du LMS utilisent les mêmes composants que le reste du site :
# pas de classes ad hoc, pas de palette parallèle, pas de style inline.
INPUT = "form-input"
INPUT_COURT = "form-input w-24"
FICHIER = "form-file"

REGLE_COPIE = RegleFichier(
    extensions=frozenset({".pdf", ".doc", ".docx", ".odt"}),
    taille_max=10 * 1024 * 1024,
    message_formats="Formats acceptés : PDF, DOC, DOCX ou ODT.",
)


class StudentSubmissionForm(FormulaireModeleITEAG):
    """Remise d'une copie étudiante pour une évaluation du LMS."""

    class Meta:
        model = Evaluation
        fields = ["fichier_soumis"]
        widgets = {
            "fichier_soumis": forms.ClearableFileInput(attrs={"class": FICHIER, "accept": REGLE_COPIE.accept})
        }

    def clean_fichier_soumis(self):
        uploaded = self.cleaned_data.get("fichier_soumis")
        if not uploaded:
            raise forms.ValidationError("Sélectionnez le fichier à remettre.")
        return valider_fichier(uploaded, REGLE_COPIE)


class RessourceUploadForm(FormulaireModeleITEAG):
    """ENS-002 — Upload de ressource pédagogique."""

    class Meta:
        model = RessourcePedagogique
        fields = ["titre", "description", "fichier", "visible_etudiants"]
        widgets = {
            "titre": forms.TextInput(attrs={"class": INPUT}),
            "description": forms.Textarea(attrs={"rows": 3, "class": INPUT}),
            "fichier": forms.ClearableFileInput(attrs={"class": FICHIER}),
        }


class GradeForm(FormulaireModeleITEAG):
    """ENS-004 — Saisie de note par l'enseignant."""

    class Meta:
        model = Evaluation
        fields = ["note", "appreciation", "ects_valides", "fichier_corrige"]
        widgets = {
            "note": forms.NumberInput(
                attrs={
                    "min": 0,
                    "max": 20,
                    "step": "0.5",
                    "class": INPUT_COURT,
                    "placeholder": "/20",
                }
            ),
            "appreciation": forms.Textarea(
                attrs={
                    "rows": 3,
                    "class": INPUT,
                    "placeholder": "Appréciation de l'enseignant…",
                }
            ),
            "ects_valides": forms.NumberInput(attrs={"min": 0, "max": 30, "step": "0.5", "class": INPUT_COURT}),
            "fichier_corrige": forms.ClearableFileInput(attrs={"accept": ".pdf,.doc,.docx,.odt,.jpg,.png"}),
        }

    def clean_note(self):
        note = self.cleaned_data.get("note")
        if note is None:
            raise forms.ValidationError("La note est obligatoire.")
        return note


class AnnonceForm(FormulaireModeleITEAG):
    """ENS-006 — Publication d'annonce."""

    contenu = ChampTexteRiche(
        label="Contenu",
        placeholder="Rédigez l'annonce destinée aux étudiants…",
        min_height="14rem",
        help_text="La mise en forme sera visible dans l'espace étudiant.",
    )

    class Meta:
        model = Annonce
        fields = ["titre", "contenu"]
        widgets = {
            "titre": forms.TextInput(attrs={"class": INPUT, "placeholder": "Titre de l'annonce"}),
        }


class ParametresEvaluationForm(FormulaireModeleITEAG):
    """Date d'examen et fenêtre de remise, fixées par l'enseignant.

    Ces trois réglages vivent sur le cours de session et non sur chaque copie :
    une échéance se décide pour la classe, pas étudiant par étudiant.
    """

    class Meta:
        model = CoursDeSession
        fields = ["date_examen", "depot_ouverture", "depot_fermeture"]
        widgets = {
            "date_examen": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
            "depot_ouverture": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
            "depot_fermeture": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Sans ce format, un champ « datetime-local » ne réaffiche pas la valeur
        # déjà enregistrée : l'enseignant croit son réglage perdu et le ressaisit.
        for nom in ("date_examen", "depot_ouverture", "depot_fermeture"):
            self.fields[nom].input_formats = ["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"]

    def clean(self):
        donnees = super().clean()
        ouverture, fermeture = donnees.get("depot_ouverture"), donnees.get("depot_fermeture")
        if ouverture and fermeture and fermeture < ouverture:
            self.add_error("depot_fermeture", "La fermeture ne peut pas précéder l'ouverture.")
        return donnees


class DevoirForm(FormulaireModeleITEAG):
    """Le travail demandé : consigne, fenêtre de dépôt, barème."""

    class Meta:
        model = Devoir
        fields = [
            "titre",
            "type_evaluation",
            "modalite",
            "consigne",
            "fichier_consigne",
            "date_ouverture",
            "date_fermeture",
            "retard_accepte",
            "bareme",
            "ects",
            "portee",
            "groupe",
            "promotion",
            "etudiants",
        ]
        widgets = {
            "titre": forms.TextInput(attrs={"class": INPUT, "placeholder": "Dissertation sur l'épître aux Romains"}),
            "consigne": forms.Textarea(attrs={"rows": 6, "class": INPUT, "placeholder": "Ce qui est attendu…"}),
            "fichier_consigne": forms.ClearableFileInput(attrs={"class": FICHIER}),
            # « datetime-local » plutôt qu'un sélecteur maison : le navigateur
            # sait déjà proposer un calendrier, dans la langue de l'utilisateur,
            # et il reste utilisable au clavier.
            "date_ouverture": forms.DateTimeInput(
                attrs={"type": "datetime-local", "class": INPUT}, format="%Y-%m-%dT%H:%M"
            ),
            "date_fermeture": forms.DateTimeInput(
                attrs={"type": "datetime-local", "class": INPUT}, format="%Y-%m-%dT%H:%M"
            ),
            "bareme": forms.NumberInput(attrs={"min": 1, "step": "0.5", "class": INPUT_COURT}),
            "ects": forms.NumberInput(attrs={"min": 0, "max": 30, "step": "0.5", "class": INPUT_COURT}),
            "portee": forms.Select(attrs={"class": INPUT}),
            "groupe": forms.Select(attrs={"class": INPUT}),
            "promotion": forms.Select(attrs={"class": INPUT}),
            "etudiants": forms.SelectMultiple(attrs={"class": INPUT, "size": 8}),
        }

    def __init__(self, *args, cours_session=None, **kwargs):
        super().__init__(*args, **kwargs)
        for nom in ("date_ouverture", "date_fermeture"):
            self.fields[nom].input_formats = ["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"]

        # Les listes de destinataires sont restreintes au cours : proposer les
        # groupes d'un autre cours ou tous les étudiants de l'institut
        # inviterait à désigner quelqu'un qui ne le suit pas.
        cours_session = cours_session or getattr(self.instance, "cours_session", None)
        if cours_session is not None and cours_session.pk:
            from apps.academics.models import ProfilEtudiant, Promotion

            inscrits = ProfilEtudiant.objects.filter(inscriptions__cours_session=cours_session).distinct()
            self.fields["groupe"].queryset = GroupeEtudiants.objects.filter(cours_session=cours_session)
            self.fields["etudiants"].queryset = inscrits.select_related("utilisateur").order_by(
                "utilisateur__last_name", "utilisateur__first_name"
            )
            self.fields["promotion"].queryset = Promotion.objects.filter(etudiants__in=inscrits).distinct()

        self.fields["groupe"].required = False
        self.fields["promotion"].required = False
        self.fields["etudiants"].required = False
        self.fields["portee"].help_text = "Le devoir ne touche jamais que des inscrits à ce cours."

    def clean(self):
        donnees = super().clean()
        ouverture, fermeture = donnees.get("date_ouverture"), donnees.get("date_fermeture")
        if ouverture and fermeture and fermeture <= ouverture:
            self.add_error("date_fermeture", "La fermeture doit suivre l'ouverture.")
        return donnees


class RevisionNoteForm(FormulaireITEAG):
    """Recours sur une note publiée. Le motif n'est pas facultatif."""

    note = forms.DecimalField(
        min_value=0,
        max_value=20,
        decimal_places=2,
        label="Nouvelle note",
        widget=forms.NumberInput(attrs={"min": 0, "max": 20, "step": "0.5", "class": INPUT_COURT}),
    )
    appreciation = forms.CharField(
        required=False,
        label="Appréciation corrigée",
        widget=forms.Textarea(attrs={"rows": 3, "class": INPUT}),
    )
    motif = forms.CharField(
        label="Motif de la révision",
        help_text="Il est conservé, communiqué à l'étudiant, et consultable en cas de contestation.",
        widget=forms.Textarea(
            attrs={"rows": 3, "class": INPUT, "placeholder": "Erreur de report, seconde lecture, recours accordé…"}
        ),
    )

    def clean_motif(self):
        motif = self.cleaned_data["motif"].strip()
        if len(motif) < 10:
            raise forms.ValidationError("Précisez le motif : il devra tenir devant l'étudiant et devant le jury.")
        return motif


class QuestionForm(FormulaireModeleITEAG):
    """Une question du questionnaire. Les propositions se saisissent à côté."""

    class Meta:
        model = Question
        fields = ["enonce", "type_question", "points", "explication", "ordre"]
        widgets = {
            "enonce": forms.Textarea(attrs={"rows": 3, "class": INPUT, "placeholder": "Formulez la question…"}),
            "type_question": forms.Select(attrs={"class": "form-select"}),
            "points": forms.NumberInput(attrs={"min": "0.25", "step": "0.25", "class": INPUT_COURT}),
            "explication": forms.Textarea(attrs={"rows": 2, "class": INPUT}),
            "ordre": forms.NumberInput(attrs={"min": 0, "class": INPUT_COURT}),
        }
        help_texts = {"ordre": "Laisser 0 pour placer la question à la fin."}


class ChoixForm(FormulaireModeleITEAG):
    class Meta:
        model = Choix
        fields = ["libelle", "correct", "ordre"]
        widgets = {
            "libelle": forms.TextInput(attrs={"class": INPUT, "placeholder": "Proposition de réponse"}),
            "ordre": forms.NumberInput(attrs={"min": 0, "class": INPUT_COURT}),
        }


class GroupeForm(FormulaireModeleITEAG):
    """Un groupe de travail au sein d'un cours."""

    class Meta:
        model = GroupeEtudiants
        fields = ["nom", "description", "membres", "couleur"]
        widgets = {
            "nom": forms.TextInput(attrs={"class": INPUT, "placeholder": "Équipe 1"}),
            "description": forms.Textarea(attrs={"rows": 3, "class": INPUT, "placeholder": "Sujet du projet…"}),
            "membres": forms.CheckboxSelectMultiple(),
            "couleur": forms.TextInput(attrs={"type": "color", "class": "form-input w-16"}),
        }

    def __init__(self, *args, cours_session=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.cours_session = cours_session or getattr(self.instance, "cours_session", None)
        # Seuls les inscrits au cours : proposer toute la promotion ferait
        # constituer des groupes avec des étudiants qui ne suivent pas ce cours.
        if self.cours_session is not None:
            from apps.academics.models import ProfilEtudiant

            self.fields["membres"].queryset = (
                ProfilEtudiant.objects.filter(inscriptions__cours_session=self.cours_session)
                .select_related("utilisateur")
                .order_by("utilisateur__last_name", "utilisateur__first_name")
            )
        self.fields["membres"].required = False


class MessageGroupeForm(FormulaireITEAG):
    """Message adressé d'un coup à tous les membres d'un groupe."""

    titre = forms.CharField(
        max_length=200,
        label="Objet",
        widget=forms.TextInput(attrs={"class": INPUT, "placeholder": "Rendez-vous de projet"}),
    )
    message = forms.CharField(
        label="Message",
        widget=forms.Textarea(attrs={"rows": 5, "class": INPUT}),
    )
