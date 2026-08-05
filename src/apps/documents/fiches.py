"""Ce que chaque genre de document exige, déclaré une fois.

Un modèle plat — un objet, un corps libre, pour tous les genres — laisse au
rédacteur la charge de se souvenir qu'une convocation porte une heure et un
lieu, qu'un compte rendu nomme ses participants, qu'une attestation désigne un
bénéficiaire. Il l'oublie, et le document part incomplet. Rien ne le rattrape :
le corps étant libre, le formulaire n'a rien à vérifier.

Chaque genre déclare donc **sa fiche** : les champs qui lui sont propres, avec
leur type et leur obligation. Le formulaire devient le schéma, et la validation
est celle de Django — pas une convention écrite dans un commentaire.

**Pourquoi du JSON plutôt qu'une table par genre.** Les champs propres à un
genre ne sont jamais interrogés en masse : on ne demande pas « tous les
documents dont le lieu est la salle B12 ». Ce qu'on cherche — la référence, la
date, le genre, l'objet — reste en colonnes. Une table par genre coûterait une
migration à chaque nouveau modèle de courrier, pour une requête que personne
n'écrit.

**Ce que le JSON ne dispense pas de faire.** Une donnée sans schéma est une
donnée qu'on finit par ne plus savoir lire. La fiche est ce schéma : elle
valide à la saisie, et elle est le seul chemin d'écriture.
"""

from __future__ import annotations

from dataclasses import dataclass

from django import forms

from apps.core.formulaires import FormulaireITEAG

INPUT = "form-input"


class FicheVide(FormulaireITEAG):
    """Aucun champ propre : le genre se contente de l'objet et du corps."""


class FicheConvocation(FormulaireITEAG):
    date_seance = forms.DateField(
        label="Date de la séance",
        widget=forms.DateInput(attrs={"class": INPUT, "type": "date"}, format="%Y-%m-%d"),
    )
    heure_seance = forms.TimeField(
        label="Heure",
        widget=forms.TimeInput(attrs={"class": INPUT, "type": "time"}, format="%H:%M"),
    )
    lieu = forms.CharField(
        max_length=200,
        label="Lieu",
        widget=forms.TextInput(attrs={"class": INPUT, "placeholder": "Salle du conseil, campus des Abymes"}),
    )
    ordre_du_jour = forms.CharField(
        required=False,
        label="Ordre du jour",
        help_text="Un point par ligne.",
        widget=forms.Textarea(attrs={"rows": 5, "class": INPUT, "placeholder": "1. Approbation du procès-verbal"}),
    )


class FicheCompteRendu(FormulaireITEAG):
    date_seance = forms.DateField(
        label="Date de la séance rapportée",
        widget=forms.DateInput(attrs={"class": INPUT, "type": "date"}, format="%Y-%m-%d"),
    )
    lieu = forms.CharField(
        required=False,
        max_length=200,
        label="Lieu",
        widget=forms.TextInput(attrs={"class": INPUT}),
    )
    participants = forms.CharField(
        label="Participants",
        help_text="Un nom par ligne. Ils figurent en tête du compte rendu.",
        widget=forms.Textarea(attrs={"rows": 5, "class": INPUT, "placeholder": "Alain Nisus, directeur"}),
    )
    excuses = forms.CharField(
        required=False,
        label="Excusés",
        help_text="Un nom par ligne.",
        widget=forms.Textarea(attrs={"rows": 3, "class": INPUT}),
    )


class FicheAttestation(FormulaireITEAG):
    beneficiaire = forms.CharField(
        max_length=200,
        label="Bénéficiaire",
        help_text="La personne que l'attestation concerne.",
        widget=forms.TextInput(attrs={"class": INPUT, "placeholder": "Madame Léonie Abaul"}),
    )
    qualite_beneficiaire = forms.CharField(
        required=False,
        max_length=200,
        label="Qualité du bénéficiaire",
        widget=forms.TextInput(attrs={"class": INPUT, "placeholder": "étudiante en licence de théologie"}),
    )
    periode = forms.CharField(
        required=False,
        max_length=200,
        label="Période concernée",
        widget=forms.TextInput(attrs={"class": INPUT, "placeholder": "année académique 2026-2027"}),
    )


class FicheNoteService(FormulaireITEAG):
    destinataires_collectifs = forms.CharField(
        max_length=250,
        label="À l'attention de",
        help_text="Le collectif visé, faute d'un destinataire nommé.",
        widget=forms.TextInput(attrs={"class": INPUT, "placeholder": "L'ensemble du corps enseignant"}),
    )
    date_effet = forms.DateField(
        required=False,
        label="Date d'effet",
        help_text="À partir de quand la note s'applique.",
        widget=forms.DateInput(attrs={"class": INPUT, "type": "date"}, format="%Y-%m-%d"),
    )


class FicheRapport(FormulaireITEAG):
    periode = forms.CharField(
        max_length=200,
        label="Période couverte",
        widget=forms.TextInput(attrs={"class": INPUT, "placeholder": "année académique 2025-2026"}),
    )
    etabli_pour = forms.CharField(
        required=False,
        max_length=200,
        label="Établi à l'attention de",
        widget=forms.TextInput(attrs={"class": INPUT, "placeholder": "Le conseil d'administration"}),
    )


class FicheInvitation(FormulaireITEAG):
    date_evenement = forms.DateField(
        label="Date de l'événement",
        widget=forms.DateInput(attrs={"class": INPUT, "type": "date"}, format="%Y-%m-%d"),
    )
    heure_evenement = forms.TimeField(
        required=False,
        label="Heure",
        widget=forms.TimeInput(attrs={"class": INPUT, "type": "time"}, format="%H:%M"),
    )
    lieu = forms.CharField(
        max_length=200,
        label="Lieu",
        widget=forms.TextInput(attrs={"class": INPUT}),
    )
    reponse_avant = forms.DateField(
        required=False,
        label="Réponse souhaitée avant le",
        widget=forms.DateInput(attrs={"class": INPUT, "type": "date"}, format="%Y-%m-%d"),
    )


@dataclass(frozen=True)
class Fiche:
    """Ce qu'un genre exige, et comment il s'imprime."""

    libelle: str
    prefixe: str
    formulaire: type[forms.Form]
    intitule_corps: str
    invite_corps: str
    description: str
    # Fragment inséré dans le PDF entre l'objet et le corps. Vide quand le
    # genre n'a rien de propre à montrer.
    partiel_pdf: str = ""

    @property
    def a_des_champs_propres(self) -> bool:
        return bool(self.formulaire.base_fields)


# Le préfixe entre dans la référence. Il est court parce qu'il se recopie à la
# main sur un registre papier et se dicte au téléphone.
FICHES: dict[str, Fiche] = {
    "courrier": Fiche(
        libelle="Courrier",
        prefixe="COU",
        formulaire=FicheVide,
        intitule_corps="Corps de la lettre",
        invite_corps="Madame, Monsieur, …",
        description="Une lettre adressée à une personne ou à un organisme.",
    ),
    "convocation": Fiche(
        libelle="Convocation",
        prefixe="CVN",
        formulaire=FicheConvocation,
        intitule_corps="Texte de la convocation",
        invite_corps="Vous êtes convoqué à…",
        description="Appelle quelqu'un à une séance : date, heure et lieu sont exigés.",
        partiel_pdf="documents/pdf/redaction/convocation.html",
    ),
    "invitation": Fiche(
        libelle="Invitation",
        prefixe="INV",
        formulaire=FicheInvitation,
        intitule_corps="Texte de l'invitation",
        invite_corps="Nous avons le plaisir de vous convier à…",
        description="Convie à un événement : date et lieu sont exigés.",
        partiel_pdf="documents/pdf/redaction/invitation.html",
    ),
    "compte_rendu": Fiche(
        libelle="Compte rendu",
        prefixe="CR",
        formulaire=FicheCompteRendu,
        intitule_corps="Compte rendu des débats",
        invite_corps="La séance est ouverte à…",
        description="Rapporte une séance : les participants sont exigés.",
        partiel_pdf="documents/pdf/redaction/compte_rendu.html",
    ),
    "note_service": Fiche(
        libelle="Note de service",
        prefixe="NS",
        formulaire=FicheNoteService,
        intitule_corps="Texte de la note",
        invite_corps="Il est rappelé que…",
        description="S'adresse à un collectif plutôt qu'à une personne nommée.",
        partiel_pdf="documents/pdf/redaction/note_service.html",
    ),
    "rapport": Fiche(
        libelle="Rapport",
        prefixe="RAP",
        formulaire=FicheRapport,
        intitule_corps="Corps du rapport",
        invite_corps="Le présent rapport porte sur…",
        description="Rend compte d'une période ou d'une mission.",
        partiel_pdf="documents/pdf/redaction/rapport.html",
    ),
    "attestation": Fiche(
        libelle="Attestation",
        prefixe="ATT",
        formulaire=FicheAttestation,
        intitule_corps="Texte de l'attestation",
        invite_corps="Je soussigné…",
        description="Atteste un fait au bénéfice de quelqu'un.",
        partiel_pdf="documents/pdf/redaction/attestation.html",
    ),
    "autre": Fiche(
        libelle="Autre document",
        prefixe="DOC",
        formulaire=FicheVide,
        intitule_corps="Corps du document",
        invite_corps="Rédigez le document ici…",
        description="Pour ce qui n'entre dans aucun des genres ci-dessus.",
    ),
}


def fiche(genre: str) -> Fiche:
    """La fiche d'un genre. Un genre inconnu retombe sur « autre ».

    Le repli plutôt qu'une exception : un genre retiré du registre ne doit pas
    rendre illisibles les documents déjà écrits sous ce genre.
    """
    return FICHES.get(genre) or FICHES["autre"]


def choix_de_genre() -> list[tuple[str, str]]:
    return [(cle, f.libelle) for cle, f in FICHES.items()]
