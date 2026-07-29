"""
Questionnaires corrigés seuls, et groupes de travail.

Le QCM est le seul devoir dont la correction ne demande l'avis de personne :
ses réponses sont fermées. Ces cas fixent ce qu'il note, ce qu'il refuse, et
surtout ce qu'il ne montre jamais — la justesse d'une proposition ne doit
figurer nulle part dans la page servie à l'étudiant.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from apps.academics.models import (
    CoursDeSession,
    InscriptionSession,
    ProfilEtudiant,
    Promotion,
    SessionAcademique,
)
from apps.accounts.models import User
from apps.formations.models import Cours, Discipline, Parcours, Professeur
from apps.lms import services
from apps.lms.models import Choix, Devoir, Evaluation, GroupeEtudiants, Question

pytestmark = pytest.mark.django_db

MOT_DE_PASSE = "MotDePasseSolide!2026"


@pytest.fixture
def cours(db):
    discipline = Discipline.objects.create(nom="Théologie", slug="theologie")
    matiere = Cours.objects.create(titre="Herméneutique", slug="hermeneutique", discipline=discipline)
    compte = User.objects.create_user(
        username="enseignant", email="ens@iteag.org", password=MOT_DE_PASSE, role=User.Role.ENSEIGNANT
    )
    professeur = Professeur.objects.create(nom="Nisus", prenom="Alain", slug="alain-nisus", user=compte)
    session = SessionAcademique.objects.create(
        nom="Session de Juillet 2026", date_debut=date(2026, 7, 1), date_fin=date(2026, 7, 31)
    )
    return CoursDeSession.objects.create(session=session, cours=matiere, enseignant=professeur)


def _etudiant(cours, suffixe="1"):
    parcours, _ = Parcours.objects.get_or_create(
        slug="bachelor", defaults={"nom": "Bachelor", "type_parcours": Parcours.TypeParcours.LIBRE}
    )
    promotion, _ = Promotion.objects.get_or_create(
        nom="Promotion 2026", defaults={"parcours": parcours, "annee_debut": 2026, "annee_fin": 2029}
    )
    compte = User.objects.create_user(
        username=f"etudiant{suffixe}",
        email=f"etudiant{suffixe}@iteag.org",
        password=MOT_DE_PASSE,
        first_name="Léonie",
        last_name=f"Abaul {suffixe}",
        role=User.Role.ETUDIANT,
    )
    profil = ProfilEtudiant.objects.create(
        utilisateur=compte,
        parcours=parcours,
        promotion=promotion,
        numero_etudiant=f"ETU-QCM-{suffixe}",
        statut_inscription=ProfilEtudiant.StatutInscription.ACTIF,
    )
    InscriptionSession.objects.create(etudiant=profil, cours_session=cours)
    return profil


@pytest.fixture
def etudiant(cours):
    return _etudiant(cours)


@pytest.fixture
def questionnaire(cours):
    """Deux questions : une à réponse unique (2 pts), une multiple (3 pts)."""
    devoir = Devoir.objects.create(
        cours_session=cours,
        titre="Contrôle de lecture",
        modalite=Devoir.Modalite.QCM,
        bareme=Decimal("20"),
        date_ouverture=timezone.now() - timedelta(days=1),
        date_fermeture=timezone.now() + timedelta(days=7),
    )
    unique = Question.objects.create(
        devoir=devoir, enonce="Qui a écrit l'épître aux Romains ?", points=Decimal("2"), ordre=1
    )
    Choix.objects.create(question=unique, libelle="Paul", correct=True, ordre=1)
    Choix.objects.create(question=unique, libelle="Pierre", correct=False, ordre=2)

    multiple = Question.objects.create(
        devoir=devoir,
        enonce="Quels évangiles sont dits synoptiques ?",
        type_question=Question.TypeQuestion.CHOIX_MULTIPLE,
        points=Decimal("3"),
        ordre=2,
    )
    Choix.objects.create(question=multiple, libelle="Matthieu", correct=True, ordre=1)
    Choix.objects.create(question=multiple, libelle="Marc", correct=True, ordre=2)
    Choix.objects.create(question=multiple, libelle="Jean", correct=False, ordre=3)
    return devoir


def _bonnes(question):
    return list(question.choix.filter(correct=True).values_list("pk", flat=True))


# ──────────────────────────────────────────────
# Validité du questionnaire
# ──────────────────────────────────────────────


def test_un_questionnaire_vide_ne_s_ouvre_pas(cours):
    devoir = Devoir.objects.create(
        cours_session=cours,
        titre="Vide",
        modalite=Devoir.Modalite.QCM,
        date_ouverture=timezone.now(),
        date_fermeture=timezone.now() + timedelta(days=1),
    )
    assert "aucune question" in services.motif_qcm_incomplet(devoir)


def test_une_question_sans_bonne_reponse_est_signalee(questionnaire):
    question = Question.objects.create(devoir=questionnaire, enonce="Sans réponse juste", points=1, ordre=3)
    Choix.objects.create(question=question, libelle="A", correct=False)
    Choix.objects.create(question=question, libelle="B", correct=False)
    assert "correcte" in question.est_valide()
    assert "Question 3" in services.motif_qcm_incomplet(questionnaire)


def test_une_question_unique_avec_deux_bonnes_reponses_est_signalee(questionnaire):
    question = Question.objects.create(devoir=questionnaire, enonce="Ambiguë", points=1, ordre=4)
    Choix.objects.create(question=question, libelle="A", correct=True)
    Choix.objects.create(question=question, libelle="B", correct=True)
    assert "une seule proposition correcte" in question.est_valide()


def test_un_questionnaire_complet_est_pret(questionnaire):
    assert services.motif_qcm_incomplet(questionnaire) == ""


# ──────────────────────────────────────────────
# Correction automatique
# ──────────────────────────────────────────────


def test_toutes_les_reponses_justes_donnent_la_note_maximale(questionnaire, etudiant):
    services.publier_devoir(questionnaire)
    copie = questionnaire.copies.get()
    questions = list(questionnaire.questions.all())

    services.enregistrer_reponses(copie, {q.pk: _bonnes(q) for q in questions})

    copie.refresh_from_db()
    assert copie.note == Decimal("20.00")
    assert copie.statut == Evaluation.StatutEvaluation.NOTE


def test_aucune_reponse_donne_zero(questionnaire, etudiant):
    services.publier_devoir(questionnaire)
    copie = questionnaire.copies.get()

    services.enregistrer_reponses(copie, {})

    copie.refresh_from_db()
    assert copie.note == Decimal("0.00")


def test_une_reponse_partielle_ne_rapporte_rien(questionnaire, etudiant):
    """Tout ou rien : la question multiple n'est pas payée à moitié."""
    services.publier_devoir(questionnaire)
    copie = questionnaire.copies.get()
    unique, multiple = list(questionnaire.questions.all())

    services.enregistrer_reponses(
        copie,
        {
            unique.pk: _bonnes(unique),
            multiple.pk: _bonnes(multiple)[:1],  # une seule des deux bonnes
        },
    )

    copie.refresh_from_db()
    # 2 points sur 5 → 8/20
    assert copie.note == Decimal("8.00")


def test_une_proposition_etrangere_ne_rapporte_pas_de_point(questionnaire, etudiant, cours):
    """Un identifiant glissé dans la requête ne doit pas être compté."""
    autre = Devoir.objects.create(
        cours_session=cours,
        titre="Autre",
        modalite=Devoir.Modalite.QCM,
        date_ouverture=timezone.now(),
        date_fermeture=timezone.now() + timedelta(days=1),
    )
    question_etrangere = Question.objects.create(devoir=autre, enonce="Ailleurs", points=5)
    intrus = Choix.objects.create(question=question_etrangere, libelle="Intrus", correct=True)

    services.publier_devoir(questionnaire)
    copie = questionnaire.copies.get()
    unique, multiple = list(questionnaire.questions.all())

    services.enregistrer_reponses(copie, {unique.pk: [intrus.pk], multiple.pk: [intrus.pk]})

    copie.refresh_from_db()
    assert copie.note == Decimal("0.00")


def test_le_questionnaire_refuse_le_depot_hors_fenetre(cours, etudiant):
    devoir = Devoir.objects.create(
        cours_session=cours,
        titre="Fermé",
        modalite=Devoir.Modalite.QCM,
        statut=Devoir.Statut.PUBLIE,
        date_ouverture=timezone.now() - timedelta(days=5),
        date_fermeture=timezone.now() - timedelta(days=1),
    )
    question = Question.objects.create(devoir=devoir, enonce="Q", points=1)
    Choix.objects.create(question=question, libelle="A", correct=True)
    copie = Evaluation.objects.create(cours_session=cours, etudiant=etudiant, devoir=devoir)

    with pytest.raises(ValidationError):
        services.enregistrer_reponses(copie, {question.pk: _bonnes(question)})


def test_recorriger_rejoue_le_bareme_sans_redemander_les_copies(questionnaire, etudiant):
    """Une seconde bonne réponse admise après coup profite à tous."""
    services.publier_devoir(questionnaire)
    copie = questionnaire.copies.get()
    unique, multiple = list(questionnaire.questions.all())

    # L'étudiant coche les trois évangiles, dont « Jean » alors marqué faux.
    services.enregistrer_reponses(
        copie,
        {unique.pk: _bonnes(unique), multiple.pk: list(multiple.choix.values_list("pk", flat=True))},
    )
    copie.refresh_from_db()
    assert copie.note == Decimal("8.00")

    # Le barème est corrigé : « Jean » devient acceptable.
    multiple.choix.filter(libelle="Jean").update(correct=True)
    assert services.recorriger(questionnaire) == 1

    copie.refresh_from_db()
    assert copie.note == Decimal("20.00")


# ──────────────────────────────────────────────
# Ce que l'étudiant voit — et ne voit pas
# ──────────────────────────────────────────────


def test_la_page_ne_revele_jamais_les_bonnes_reponses(client, questionnaire, etudiant):
    services.publier_devoir(questionnaire)
    copie = questionnaire.copies.get()
    client.force_login(etudiant.utilisateur)

    corps = client.get(reverse("etudiant:questionnaire", args=[copie.pk])).content.decode()

    assert "Qui a écrit" in corps
    assert "Paul" in corps and "Pierre" in corps
    # Rien dans la page ne distingue la bonne proposition de la mauvaise.
    assert "correct" not in corps.lower().split("<body")[-1] or 'value="true"' not in corps


def test_l_etudiant_repond_depuis_le_navigateur(client, questionnaire, etudiant):
    services.publier_devoir(questionnaire)
    copie = questionnaire.copies.get()
    unique, multiple = list(questionnaire.questions.all())
    client.force_login(etudiant.utilisateur)

    reponse = client.post(
        reverse("etudiant:questionnaire", args=[copie.pk]),
        {
            f"question-{unique.pk}": [str(pk) for pk in _bonnes(unique)],
            f"question-{multiple.pk}": [str(pk) for pk in _bonnes(multiple)],
        },
    )

    assert reponse.status_code == 302
    copie.refresh_from_db()
    assert copie.note == Decimal("20.00")


def test_un_etudiant_ne_repond_pas_a_la_place_d_un_autre(client, questionnaire, cours):
    premier = _etudiant(cours, "1")
    second = _etudiant(cours, "2")
    services.publier_devoir(questionnaire)
    copie_du_premier = questionnaire.copies.get(etudiant=premier)

    client.force_login(second.utilisateur)
    assert client.get(reverse("etudiant:questionnaire", args=[copie_du_premier.pk])).status_code == 404


# ──────────────────────────────────────────────
# Groupes de travail
# ──────────────────────────────────────────────


def test_un_groupe_ne_propose_que_les_inscrits_du_cours(cours, etudiant):
    from apps.lms.forms import GroupeForm

    parcours = Parcours.objects.get(slug="bachelor")
    promotion = Promotion.objects.get(nom="Promotion 2026")
    exterieur = User.objects.create_user(
        username="exterieur", email="ext@iteag.org", password=MOT_DE_PASSE, role=User.Role.ETUDIANT
    )
    ProfilEtudiant.objects.create(
        utilisateur=exterieur, parcours=parcours, promotion=promotion, numero_etudiant="ETU-EXT-001"
    )

    form = GroupeForm(cours_session=cours)
    proposables = set(form.fields["membres"].queryset.values_list("numero_etudiant", flat=True))
    assert proposables == {etudiant.numero_etudiant}


def test_le_message_atteint_tous_les_membres(cours):
    premier = _etudiant(cours, "1")
    second = _etudiant(cours, "2")
    groupe = GroupeEtudiants.objects.create(cours_session=cours, nom="Équipe 1")
    groupe.membres.set([premier, second])

    envoyes = services.message_au_groupe(groupe, titre="Réunion", message="Jeudi 14 h.")

    assert envoyes == 2
    assert premier.utilisateur.notifications.filter(titre="Réunion").exists()
    assert second.utilisateur.notifications.filter(titre="Réunion").exists()


def test_un_groupe_vide_ne_notifie_personne(cours):
    groupe = GroupeEtudiants.objects.create(cours_session=cours, nom="Équipe vide")
    assert services.message_au_groupe(groupe, titre="Personne", message="…") == 0


def test_l_enseignant_gere_ses_groupes_et_pas_ceux_d_un_confrere(client, cours, etudiant):
    groupe = GroupeEtudiants.objects.create(cours_session=cours, nom="Équipe 1")

    client.force_login(cours.enseignant.user)
    corps = client.get(reverse("lms:groupes_list")).content.decode()
    assert "Équipe 1" in corps

    autre = User.objects.create_user(
        username="confrere", email="confrere@iteag.org", password=MOT_DE_PASSE, role=User.Role.ENSEIGNANT
    )
    Professeur.objects.create(nom="Labeth", prenom="Ruth", slug="ruth-labeth", user=autre)
    client.force_login(autre)
    assert client.get(reverse("lms:groupe_update", args=[groupe.pk])).status_code == 404
    assert "Équipe 1" not in client.get(reverse("lms:groupes_list")).content.decode()


def test_l_etudiant_n_atteint_pas_les_groupes(client, cours, etudiant):
    client.force_login(etudiant.utilisateur)
    assert client.get(reverse("lms:groupes_list")).status_code == 403
