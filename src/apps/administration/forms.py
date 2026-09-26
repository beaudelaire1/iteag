from pathlib import Path

from django import forms
from django.contrib.auth.password_validation import validate_password
from django.utils.text import slugify

from apps.academics.models import (
    VAE,
    CoursDeSession,
    CreditECTS,
    DemandeInscriptionCours,
    Paiement,
    ProfilEtudiant,
    Promotion,
    SessionAcademique,
    Stage,
)
from apps.accounts.models import User
from apps.core.formulaires import FormulaireITEAG, FormulaireModeleITEAG
from apps.formations.models import Cours, Discipline, Parcours, Professeur, Tarif


class SlugDeriveDuNom:
    """Le secrétariat nomme, il n'a pas à inventer d'adresse : le slug se déduit.

    L'adresse déduite est rendue unique (« homiletique-2 ») : deux cours de
    même titre refusaient l'enregistrement avec une erreur sur un champ que
    personne n'avait rempli.
    """

    champ_source: str | tuple[str, ...] = "nom"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["slug"].required = False
        self.fields["slug"].label = "Adresse de la page web"
        self.fields["slug"].help_text = "Laisser vide : elle se déduit du nom."

    def _texte_source(self) -> str:
        sources = (self.champ_source,) if isinstance(self.champ_source, str) else self.champ_source
        return " ".join(self.data.get(self.add_prefix(nom), "") for nom in sources).strip()

    def clean_slug(self):
        slug = self.cleaned_data.get("slug")
        if slug:
            return slug
        longueur = self.fields["slug"].max_length
        base = slugify(self._texte_source())[: longueur - 4] or "element"
        modele = self._meta.model
        existants = modele.objects.exclude(pk=self.instance.pk) if self.instance.pk else modele.objects.all()
        candidat, rang = base, 2
        while existants.filter(slug=candidat).exists():
            candidat, rang = f"{base}-{rang}", rang + 1
        return candidat


class AdminUserForm(FormulaireModeleITEAG):
    password1 = forms.CharField(
        label="Mot de passe",
        widget=forms.PasswordInput(attrs={"class": "form-input"}),
        required=False,
        help_text="Laisser vide pour ne pas modifier.",
    )

    class Meta:
        model = User
        fields = ["username", "first_name", "last_name", "email", "phone", "role", "is_active"]
        widgets = {
            "username": forms.TextInput(attrs={"class": "form-input"}),
            "first_name": forms.TextInput(attrs={"class": "form-input"}),
            "last_name": forms.TextInput(attrs={"class": "form-input"}),
            "email": forms.EmailInput(attrs={"class": "form-input"}),
            "phone": forms.TextInput(attrs={"class": "form-input"}),
            "role": forms.Select(attrs={"class": "form-input"}),
            "is_active": forms.CheckboxInput(attrs={"class": "h-4 w-4 rounded"}),
        }

    def __init__(self, *args, auteur=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.auteur = auteur
        # Le secrétariat tient les comptes, mais ne peut pas se hisser au rang
        # qu'il administre : sans cela, la séparation des rôles ne tiendrait
        # qu'à la bonne volonté de celui qui remplit le formulaire.
        if self._auteur_est_secretariat():
            self.fields["role"].choices = [
                (valeur, libelle) for valeur, libelle in User.Role.choices if valeur != User.Role.ADMIN
            ]

    def _auteur_est_secretariat(self) -> bool:
        return bool(self.auteur and not self.auteur.is_superuser and self.auteur.role == User.Role.SECRETARIAT)

    def clean_role(self):
        role = self.cleaned_data.get("role")
        if role == User.Role.ADMIN and self._auteur_est_secretariat():
            raise forms.ValidationError("Seule la direction peut attribuer le rôle d'administrateur.")
        return role

    def clean(self):
        donnees = super().clean()
        if self.instance.pk and self.instance.is_superuser and not getattr(self.auteur, "is_superuser", False):
            raise forms.ValidationError("Un superutilisateur ne se modifie que depuis un autre superutilisateur.")
        if self.instance.pk and self.instance.role == User.Role.ADMIN and self._auteur_est_secretariat():
            raise forms.ValidationError("Un compte de direction ne se modifie que depuis la direction.")
        return donnees

    def save(self, commit=True):
        user = super().save(commit=False)
        pw = self.cleaned_data.get("password1")
        if pw:
            user.set_password(pw)
        if commit:
            user.save()
        return user

    def clean_password1(self):
        password = self.cleaned_data.get("password1")
        if password:
            validate_password(password, self.instance)
        return password


class AdminUserCreateForm(AdminUserForm):
    password1 = forms.CharField(
        label="Mot de passe",
        widget=forms.PasswordInput(attrs={"class": "form-input"}),
        required=True,
    )


class AdminSessionForm(FormulaireModeleITEAG):
    """Une session intensive (Carnaval, Pâques, Juillet, Toussaint).

    La période et les dates suffisent : le nom (« Session de Pâques 2027 ») et
    l'année académique (« 2026-2027 ») s'en déduisent, comme le secrétariat
    les écrivait déjà à la main.
    """

    champs_avances = ("nom", "annee_academique", "statut")

    NOMS_PERIODE = {
        SessionAcademique.Periode.CARNAVAL: "Carnaval",
        SessionAcademique.Periode.PAQUES: "Pâques",
        SessionAcademique.Periode.JUILLET: "Juillet",
        SessionAcademique.Periode.TOUSSAINT: "Toussaint",
    }

    class Meta:
        model = SessionAcademique
        fields = ["periode", "date_debut", "date_fin", "nom", "annee_academique", "statut"]
        labels = {
            "periode": "Période de la session",
            "date_debut": "Premier jour",
            "date_fin": "Dernier jour",
            "nom": "Nom de la session",
            "annee_academique": "Année académique",
            "statut": "État de la session",
        }
        widgets = {
            "annee_academique": forms.TextInput(attrs={"placeholder": "2026-2027"}),
            "date_debut": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "date_fin": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["nom"].required = False
        self.fields["nom"].help_text = "Laisser vide : « Session de Pâques 2027 », d'après la période et la date."
        self.fields["annee_academique"].required = False
        self.fields["annee_academique"].help_text = "Laisser vide : déduite du premier jour (rentrée en août)."

    def clean(self):
        donnees = super().clean()
        debut, fin, periode = donnees.get("date_debut"), donnees.get("date_fin"), donnees.get("periode")
        if debut and fin and fin < debut:
            self.add_error("date_fin", "Le dernier jour ne peut pas précéder le premier.")
        if debut and not donnees.get("annee_academique"):
            annee = debut.year if debut.month >= 8 else debut.year - 1
            donnees["annee_academique"] = f"{annee}-{annee + 1}"
        if debut and periode and not donnees.get("nom"):
            donnees["nom"] = f"Session de {self.NOMS_PERIODE.get(periode, periode)} {debut.year}"
        return donnees


class AdminProfesseurForm(SlugDeriveDuNom, FormulaireModeleITEAG):
    """Fiche publique d'un enseignant.

    L'adresse de la page se déduit du prénom et du nom ; le compte lié, l'ordre
    d'affichage et la mise en ligne gardent leurs valeurs habituelles.
    """

    champ_source = ("prenom", "nom")
    champs_avances = ("user", "actif", "ordre", "slug")

    class Meta:
        model = Professeur
        fields = ["prenom", "nom", "specialite", "biographie", "photo", "disciplines", "user", "actif", "ordre", "slug"]
        labels = {
            "specialite": "Spécialité",
            "biographie": "Présentation",
            "disciplines": "Disciplines enseignées",
            "user": "Compte de connexion de l'enseignant",
            "actif": "Fiche affichée sur le site",
            "ordre": "Rang dans la liste des enseignants",
        }
        help_texts = {
            "specialite": "Par exemple « Ancien Testament ».",
            "user": "Relie la fiche au compte avec lequel l'enseignant se connecte.",
            "ordre": "0 place l'enseignant en tête ; les rangs égaux se classent par nom.",
        }
        widgets = {
            "biographie": forms.Textarea(attrs={"rows": 5}),
            "disciplines": forms.CheckboxSelectMultiple(),
            "ordre": forms.NumberInput(attrs={"min": 0}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["user"].queryset = User.objects.filter(role=User.Role.ENSEIGNANT)
        self.fields["user"].required = False


class AdminEtudiantForm(FormulaireModeleITEAG):
    """Modification d'un dossier étudiant existant.

    Le compte rattaché ne se change plus ici : réattribuer un dossier — ses
    notes, ses crédits, ses paiements — à une autre personne n'est pas une
    correction de fiche. Le nom et le courriel se modifient depuis
    « Comptes utilisateurs ».
    """

    champs_avances = ("numero_etudiant", "formule_tarif", "eglise_fondatrice")

    class Meta:
        model = ProfilEtudiant
        fields = [
            "parcours",
            "promotion",
            "statut_inscription",
            "eglise",
            "numero_etudiant",
            "formule_tarif",
            "eglise_fondatrice",
        ]
        labels = {
            "statut_inscription": "Situation de l'étudiant",
            "eglise": "Église d'appartenance",
            "formule_tarif": "Formule de tarif",
        }


class InscriptionEtudiantForm(FormulaireITEAG):
    """Inscrire un étudiant en une seule fois : compte et dossier.

    L'ancien écran exigeait de choisir un compte déjà créé ailleurs, puis
    d'inventer un numéro étudiant. Ici, on saisit la personne ; le compte, le
    numéro (ETU2026001…) et le courriel d'activation suivent, comme à l'import
    d'un tableur ou à l'acceptation d'une candidature.
    """

    champs_avances = ("statut_inscription", "formule_tarif", "eglise_fondatrice")

    prenom = forms.CharField(label="Prénom", max_length=150)
    nom = forms.CharField(label="Nom", max_length=150)
    email = forms.EmailField(
        label="Adresse électronique",
        help_text="L'étudiant y recevra le lien pour choisir son mot de passe.",
    )
    telephone = forms.CharField(label="Téléphone", max_length=20, required=False)
    parcours = forms.ModelChoiceField(
        label="Parcours",
        queryset=Parcours.objects.filter(actif=True).order_by("nom"),
        required=False,
    )
    promotion = forms.ModelChoiceField(
        label="Promotion",
        queryset=Promotion.objects.filter(actif=True).select_related("parcours").order_by("-annee_debut", "nom"),
        required=False,
    )
    eglise = forms.CharField(label="Église d'appartenance", max_length=200, required=False)
    envoyer_invitation = forms.BooleanField(
        label="Envoyer maintenant le courriel d'activation à l'étudiant",
        required=False,
        initial=True,
    )
    statut_inscription = forms.ChoiceField(
        label="Situation de l'étudiant",
        choices=ProfilEtudiant.StatutInscription.choices,
        initial=ProfilEtudiant.StatutInscription.INSCRIT,
    )
    formule_tarif = forms.ModelChoiceField(
        label="Formule de tarif",
        queryset=Tarif.objects.filter(actif=True),
        required=False,
    )
    eglise_fondatrice = forms.BooleanField(label="Membre d'une Église fondatrice", required=False)

    def clean_email(self):
        email = self.cleaned_data["email"].strip()
        compte = User.objects.filter(email__iexact=email).first()
        if compte is None:
            return email
        profil = getattr(compte, "profil_etudiant", None)
        if profil is not None:
            raise forms.ValidationError(
                f"Cette adresse est déjà celle de l'étudiant {compte.get_full_name()} (n° {profil.numero_etudiant})."
            )
        if compte.role != User.Role.ETUDIANT:
            raise forms.ValidationError(f"Cette adresse appartient déjà à un compte « {compte.get_role_display()} ».")
        return email

    def clean(self):
        donnees = super().clean()
        parcours, promotion = donnees.get("parcours"), donnees.get("promotion")
        if promotion and parcours and promotion.parcours_id != parcours.pk:
            self.add_error("promotion", f"Cette promotion appartient au parcours « {promotion.parcours} ».")
        if promotion and not parcours:
            donnees["parcours"] = promotion.parcours
        return donnees


class AdminCoursForm(SlugDeriveDuNom, FormulaireModeleITEAG):
    """Un cours du référentiel.

    Seuls le titre, la discipline et les parcours sont à fournir : l'adresse
    web se déduit du titre, les 2,5 ECTS sont la règle de l'institut (CDC
    §2.2) et un cours créé est proposé d'office. Ces réglages restent sous
    « Plus d'options » pour les exceptions.
    """

    champs_avances = ("code", "ects", "actif", "slug")

    class Meta:
        model = Cours
        fields = ["titre", "discipline", "parcours", "description", "objectifs", "code", "ects", "actif", "slug"]
        labels = {
            "titre": "Titre du cours",
            "parcours": "Parcours où ce cours est enseigné",
            "description": "Présentation du cours",
            "objectifs": "Objectifs pédagogiques",
            "code": "Code du cours",
            "ects": "Crédits ECTS",
            "actif": "Cours proposé au catalogue",
        }
        help_texts = {
            "description": "Affichée sur la page publique du cours. Peut être complétée plus tard.",
            "objectifs": "Facultatif.",
            "code": "Facultatif, par exemple « AT-101 ».",
            "ects": "2,5 pour tout cours de l'ITEAG, sauf exception.",
            "actif": "Décocher pour retirer le cours du catalogue sans le supprimer.",
        }
        widgets = {
            "parcours": forms.CheckboxSelectMultiple(),
            "description": forms.Textarea(attrs={"rows": 5}),
            "objectifs": forms.Textarea(attrs={"rows": 4}),
            "ects": forms.NumberInput(attrs={"min": 0, "step": "0.5"}),
        }

    champ_source = "titre"


class AdminDisciplineForm(SlugDeriveDuNom, FormulaireModeleITEAG):
    champs_avances = ("ordre", "slug")

    class Meta:
        model = Discipline
        fields = ["nom", "description", "ordre", "slug"]
        labels = {"nom": "Nom de la discipline", "ordre": "Rang dans la liste"}
        widgets = {
            "description": forms.Textarea(attrs={"rows": 4}),
            "ordre": forms.NumberInput(attrs={"min": 0}),
        }


class AdminParcoursForm(SlugDeriveDuNom, FormulaireModeleITEAG):
    champs_avances = ("ects_requis", "duree_annees", "actif", "meta_description", "slug")

    class Meta:
        model = Parcours
        fields = [
            "nom",
            "type_parcours",
            "description",
            "conditions_entree",
            "ects_requis",
            "duree_annees",
            "actif",
            "meta_description",
            "slug",
        ]
        labels = {
            "nom": "Nom du parcours",
            "type_parcours": "Type de parcours",
            "description": "Présentation",
            "conditions_entree": "Conditions d'entrée",
            "ects_requis": "Crédits ECTS pour obtenir le diplôme",
            "duree_annees": "Durée (en années)",
            "actif": "Parcours proposé aux candidats",
            "meta_description": "Résumé pour les moteurs de recherche",
        }
        help_texts = {
            "meta_description": "Une phrase affichée par Google sous le titre de la page. Facultatif.",
        }
        widgets = {
            "description": forms.Textarea(attrs={"rows": 5}),
            "conditions_entree": forms.Textarea(attrs={"rows": 4}),
            "ects_requis": forms.NumberInput(attrs={"min": 0}),
            "duree_annees": forms.NumberInput(attrs={"min": 1}),
        }


class CoursDeSessionForm(FormulaireModeleITEAG):
    """Programmer un cours dans une session.

    Quatre questions suffisent : quel cours, dans quelle session, avec quel
    enseignant, et comment. Capacité, date limite, frais particuliers, délai
    de correction et état du cours gardent les valeurs habituelles de
    l'institut, rangées sous « Plus d'options ».
    """

    champs_avances = (
        "capacite",
        "inscriptions_ouvertes",
        "date_limite_inscription",
        "frais_inscription",
        "delai_correction_jours",
        "statut",
        "informations_pratiques",
    )

    # Redéclaré pour rester facultatif : un cours créé sans y penser garde le
    # délai par défaut de l'institut plutôt que de refuser l'enregistrement.
    delai_correction_jours = forms.IntegerField(
        required=False,
        min_value=0,
        label="Délai de correction (jours)",
        help_text="Au-delà, une copie remise et non notée est signalée au secrétariat. Zéro : aucun suivi.",
        widget=forms.NumberInput(attrs={"min": 0}),
    )

    def clean_delai_correction_jours(self):
        valeur = self.cleaned_data.get("delai_correction_jours")
        if valeur is None:
            return CoursDeSession._meta.get_field("delai_correction_jours").default
        return valeur

    class Meta:
        model = CoursDeSession
        fields = [
            "cours",
            "session",
            "enseignant",
            "modalite",
            "horaires",
            "salle",
            "capacite",
            "inscriptions_ouvertes",
            "date_limite_inscription",
            "frais_inscription",
            # Le délai au-delà duquel une copie remise et non notée remonte au
            # secrétariat. Il se règle ici, et non sur l'écran de l'enseignant :
            # personne ne fixe l'échéance qu'on lui opposera ensuite.
            "delai_correction_jours",
            "statut",
            "informations_pratiques",
        ]
        labels = {
            "cours": "Quel cours ?",
            "session": "Pendant quelle session ?",
            "enseignant": "Quel enseignant ?",
            "modalite": "Comment le cours a-t-il lieu ?",
            "horaires": "Jours et horaires",
            "salle": "Salle ou lieu",
            "capacite": "Nombre de places",
            "inscriptions_ouvertes": "Les étudiants peuvent s'inscrire",
            "frais_inscription": "Frais particuliers (€)",
            "statut": "État du cours",
        }
        help_texts = {
            "horaires": "Par exemple « Lundi au vendredi, 9 h – 12 h ». Facultatif.",
            "salle": "Facultatif.",
        }
        widgets = {
            "horaires": forms.Textarea(attrs={"rows": 2}),
            "capacite": forms.NumberInput(attrs={"min": 1}),
            "date_limite_inscription": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "frais_inscription": forms.NumberInput(attrs={"min": 0, "step": "0.01"}),
            "informations_pratiques": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        instance = self.instance
        # Les listes ne proposent que ce qu'on programme vraiment : sessions à
        # venir ou en cours, cours au catalogue, enseignants en activité. La
        # valeur déjà enregistrée reste toujours proposée, même retirée.
        sessions = SessionAcademique.objects.exclude(statut=SessionAcademique.StatutSession.TERMINEE)
        cours = Cours.objects.filter(actif=True)
        enseignants = Professeur.objects.filter(actif=True)
        if instance.pk:
            sessions = sessions | SessionAcademique.objects.filter(pk=instance.session_id)
            cours = cours | Cours.objects.filter(pk=instance.cours_id)
            enseignants = enseignants | Professeur.objects.filter(pk=instance.enseignant_id)
        self.fields["session"].queryset = sessions.distinct().order_by("date_debut")
        self.fields["cours"].queryset = cours.distinct().order_by("titre")
        self.fields["enseignant"].queryset = enseignants.distinct().order_by("nom", "prenom")


class PaiementForm(FormulaireModeleITEAG):
    """Un règlement reçu d'un étudiant."""

    champs_avances = ("reference", "recu_pdf")

    class Meta:
        model = Paiement
        fields = ["etudiant", "montant", "date_paiement", "mode", "session", "statut", "reference", "recu_pdf"]
        labels = {
            "etudiant": "Étudiant qui a payé",
            "montant": "Montant reçu (€)",
            "date_paiement": "Date du paiement",
            "mode": "Moyen de paiement",
            "session": "Session réglée",
            "statut": "Où en est ce paiement ?",
            "reference": "Référence du virement",
            "recu_pdf": "Reçu (fichier PDF)",
        }
        help_texts = {
            "session": "Permet de rattacher le paiement aux inscriptions de cette session.",
            "statut": "« Confirmé » quand l'argent est bien arrivé sur le compte de l'institut.",
            "reference": "Telle qu'elle apparaît sur le relevé bancaire. Facultatif.",
        }
        widgets = {
            "montant": forms.NumberInput(attrs={"min": 0, "step": "0.01"}),
            "date_paiement": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "recu_pdf": forms.ClearableFileInput(attrs={"accept": ".pdf"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["etudiant"].queryset = ProfilEtudiant.objects.select_related("utilisateur").order_by(
            "utilisateur__last_name", "utilisateur__first_name"
        )
        self.fields["session"].queryset = SessionAcademique.objects.order_by("-date_debut")
        if not self.instance.pk and not self.initial.get("date_paiement"):
            from django.utils import timezone

            self.initial["date_paiement"] = timezone.localdate()

    def clean_recu_pdf(self):
        uploaded = self.cleaned_data.get("recu_pdf")
        if not uploaded:
            return uploaded
        if uploaded.size > 5 * 1024 * 1024:
            raise forms.ValidationError("Le reçu ne doit pas dépasser 5 Mo.")
        if Path(uploaded.name).suffix.lower() != ".pdf":
            raise forms.ValidationError("Le reçu doit être un fichier PDF.")
        return uploaded


class ChoixAvecConfirmation(forms.RadioSelect):
    """Boutons radio dont chaque option peut porter sa question de confirmation.

    Le script de confirmation lit « data-confirmer » sur l'option cochée : la
    question dit ce que ce choix-là va déclencher.
    """

    def __init__(self, *args, confirmations=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.confirmations = confirmations or {}

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex=subindex, attrs=attrs)
        question = self.confirmations.get(str(value))
        if question:
            option["attrs"]["data-confirmer"] = question
        return option


class EnrollmentDecisionForm(FormulaireITEAG):
    ACTIONS = [
        ("demander_paiement", "Valider administrativement et demander le paiement"),
        ("confirmer", "Confirmer l'inscription"),
        ("refuser", "Refuser la demande"),
        ("reouvrir", "Rouvrir la demande"),
    ]

    ACTIONS_PAR_STATUT = {
        DemandeInscriptionCours.Statut.SOUMISE: {"demander_paiement", "confirmer", "refuser"},
        DemandeInscriptionCours.Statut.PAIEMENT_ATTENTE: {"confirmer", "refuser"},
        DemandeInscriptionCours.Statut.CONFIRMEE: set(),
        DemandeInscriptionCours.Statut.REFUSEE: {"reouvrir"},
        DemandeInscriptionCours.Statut.ANNULEE: {"reouvrir"},
    }

    # Des boutons radio plutôt qu'une liste : la liste présélectionnait la
    # première décision, et « Appliquer » la prenait sans qu'on l'ait choisie.
    action = forms.ChoiceField(
        label="Votre décision",
        choices=ACTIONS,
        widget=ChoixAvecConfirmation(
            attrs={"class": "form-checkbox"},
            confirmations={
                "demander_paiement": "L'étudiant va être prévenu qu'un paiement est attendu. Continuer ?",
                "confirmer": "Confirmer l'inscription ? L'étudiant sera inscrit au cours et prévenu.",
                "refuser": "Refuser cette demande ? L'étudiant sera prévenu.",
            },
        ),
    )
    paiement = forms.ModelChoiceField(
        queryset=Paiement.objects.none(),
        required=False,
        label="Paiement correspondant",
        widget=forms.Select(attrs={"class": "form-input"}),
        help_text="Facultatif : le dernier paiement confirmé compatible sera sinon utilisé automatiquement.",
    )
    exonere_paiement = forms.BooleanField(
        required=False,
        label="Dispenser l'étudiant de payer ce cours",
        widget=forms.CheckboxInput(attrs={"class": "h-4 w-4 rounded"}),
    )
    commentaire = forms.CharField(
        required=False,
        label="Motif ou commentaire",
        widget=forms.Textarea(attrs={"class": "form-input", "rows": 4}),
        help_text="Obligatoire pour un refus ou une dispense de paiement.",
    )

    def __init__(self, *args, demande: DemandeInscriptionCours, **kwargs):
        super().__init__(*args, **kwargs)
        self.demande = demande
        actions_autorisees = self.ACTIONS_PAR_STATUT.get(demande.statut, set())
        self.fields["action"].choices = [
            (valeur, libelle) for valeur, libelle in self.ACTIONS if valeur in actions_autorisees
        ]
        self.fields["paiement"].queryset = Paiement.objects.filter(
            etudiant=demande.etudiant,
            session=demande.cours_session.session,
            statut=Paiement.StatutPaiement.CONFIRME,
        ).order_by("-date_paiement")


class PromotionForm(FormulaireModeleITEAG):
    """
    Cohorte d'étudiants.

    Sans promotion en base, aucune candidature ne peut être acceptée : le
    secrétariat choisit une promotion à l'admission, et la liste ne pouvait
    jusqu'ici être remplie que depuis l'administration Django.

    Le nom se déduit du parcours et des années (« Promotion 2026-2032 — ITEAG
    Pro ») quand on le laisse vide.
    """

    champs_avances = ("nom", "actif")

    class Meta:
        model = Promotion
        fields = ["parcours", "annee_debut", "annee_fin", "nom", "actif"]
        labels = {
            "annee_debut": "Année d'entrée",
            "annee_fin": "Année de sortie prévue",
            "nom": "Nom de la promotion",
            "actif": "Promotion ouverte aux nouveaux étudiants",
        }
        widgets = {
            "nom": forms.TextInput(attrs={"placeholder": "Promotion 2026-2032"}),
            "annee_debut": forms.NumberInput(attrs={"min": 2000, "max": 2100}),
            "annee_fin": forms.NumberInput(attrs={"min": 2000, "max": 2100}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["nom"].required = False
        self.fields["nom"].help_text = "Laisser vide : il se déduit du parcours et des années."

    def clean(self):
        donnees = super().clean()
        debut, fin = donnees.get("annee_debut"), donnees.get("annee_fin")
        if debut and fin and fin < debut:
            raise forms.ValidationError({"annee_fin": "L'année de fin ne peut pas précéder l'année de début."})
        parcours = donnees.get("parcours")
        if debut and fin and parcours and not donnees.get("nom"):
            nom = f"Promotion {debut}-{fin} — {parcours.nom}"
            if Promotion.objects.filter(nom=nom).exclude(pk=self.instance.pk).exists():
                self.add_error("nom", "Une promotion porte déjà ce nom : précisez-en un autre.")
            donnees["nom"] = nom
        return donnees


class TarifForm(FormulaireModeleITEAG):
    """Grille tarifaire — CDC §2.6. Affichée au public, donc éditable sans développeur."""

    class Meta:
        model = Tarif
        fields = ["formule", "type_membre", "montant_session", "actif"]
        widgets = {
            "formule": forms.Select(attrs={"class": "form-input"}),
            "type_membre": forms.Select(attrs={"class": "form-input"}),
            "montant_session": forms.NumberInput(attrs={"class": "form-input", "min": 0, "step": "0.01"}),
            "actif": forms.CheckboxInput(attrs={"class": "h-4 w-4 rounded"}),
        }


class CreditECTSForm(FormulaireModeleITEAG):
    """
    Saisie manuelle d'un crédit.

    Les crédits ITEAG sont portés automatiquement à la publication des notes.
    Ce formulaire couvre les deux cas que l'automatisme ne peut pas traiter :
    les crédits **FLTE**, acquis hors de l'institut — le suivi croisé est une
    exigence du CDC §9.1 — et les corrections de dossier.
    """

    class Meta:
        model = CreditECTS
        fields = ["etudiant", "cours", "session", "ects_obtenus", "source", "date_validation"]
        widgets = {
            "etudiant": forms.Select(attrs={"class": "form-input"}),
            "cours": forms.Select(attrs={"class": "form-input"}),
            "session": forms.Select(attrs={"class": "form-input"}),
            "ects_obtenus": forms.NumberInput(attrs={"class": "form-input", "min": 0, "step": "0.5"}),
            "source": forms.Select(attrs={"class": "form-input"}),
            "date_validation": forms.DateInput(attrs={"class": "form-input", "type": "date"}),
        }

    def clean_ects_obtenus(self):
        montant = self.cleaned_data["ects_obtenus"]
        if montant <= 0:
            raise forms.ValidationError("Un crédit porté au dossier doit être strictement positif.")
        return montant

    def clean(self):
        donnees = super().clean()
        # La contrainte d'unicité ne couvre que les crédits rattachés à un
        # cours ET une session. Le message d'erreur brut d'une violation de
        # contrainte n'aide personne : on le devance ici.
        etudiant, cours, session = donnees.get("etudiant"), donnees.get("cours"), donnees.get("session")
        if etudiant and cours and session:
            doublons = CreditECTS.objects.filter(
                etudiant=etudiant, cours=cours, session=session, source=donnees.get("source")
            )
            if self.instance.pk:
                doublons = doublons.exclude(pk=self.instance.pk)
            if doublons.exists():
                raise forms.ValidationError("Ce cours est déjà crédité pour cet étudiant sur cette session.")
        return donnees


class StageForm(FormulaireModeleITEAG):
    """Convention de stage — CDC §2.5, 30 ECTS. Tenue par le secrétariat."""

    champs_avances = ("tuteur", "ects")

    class Meta:
        model = Stage
        fields = ["etudiant", "type_stage", "lieu", "date_debut", "date_fin", "statut", "tuteur", "ects"]
        labels = {
            "etudiant": "Étudiant",
            "type_stage": "Type de stage",
            "lieu": "Lieu du stage",
            "date_debut": "Début",
            "date_fin": "Fin",
            "statut": "Où en est le stage ?",
            "tuteur": "Enseignant tuteur",
            "ects": "Crédits ECTS",
        }
        help_texts = {"ects": "30 pour le stage obligatoire (CDC §2.5)."}
        widgets = {
            "type_stage": forms.TextInput(attrs={"placeholder": "Stage pastoral"}),
            "date_debut": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "date_fin": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "ects": forms.NumberInput(attrs={"min": 0, "step": "0.5"}),
        }

    def clean(self):
        donnees = super().clean()
        debut, fin = donnees.get("date_debut"), donnees.get("date_fin")
        if debut and fin and fin < debut:
            raise forms.ValidationError({"date_fin": "La fin du stage ne peut pas précéder son début."})
        return donnees


class VAEForm(FormulaireModeleITEAG):
    """
    Validation des acquis — CDC §2.5. Réservée à l'administration.

    Les ECTS accordés sont bornés par les ECTS demandés : accorder plus que
    demandé n'a pas de sens et signalerait une erreur de saisie.
    """

    class Meta:
        model = VAE
        fields = ["etudiant", "description_experience", "ects_demandes", "ects_accordes", "statut", "date_decision"]
        widgets = {
            "etudiant": forms.Select(attrs={"class": "form-input"}),
            "description_experience": forms.Textarea(attrs={"class": "form-input", "rows": 6}),
            "ects_demandes": forms.NumberInput(attrs={"class": "form-input", "min": 0, "step": "0.5"}),
            "ects_accordes": forms.NumberInput(attrs={"class": "form-input", "min": 0, "step": "0.5"}),
            "statut": forms.Select(attrs={"class": "form-input"}),
            "date_decision": forms.DateInput(attrs={"class": "form-input", "type": "date"}),
        }

    def clean(self):
        donnees = super().clean()
        demandes, accordes = donnees.get("ects_demandes"), donnees.get("ects_accordes")
        if demandes is not None and accordes is not None and accordes > demandes:
            raise forms.ValidationError(
                {"ects_accordes": "On ne peut pas accorder plus d'ECTS que le candidat n'en a demandé."}
            )
        if donnees.get("statut") == VAE.StatutVAE.ACCORDE:
            if not accordes:
                raise forms.ValidationError(
                    {"ects_accordes": "Une VAE accordée doit porter un nombre d'ECTS supérieur à zéro."}
                )
            if not donnees.get("date_decision"):
                raise forms.ValidationError({"date_decision": "Une décision accordée doit être datée."})
        return donnees
