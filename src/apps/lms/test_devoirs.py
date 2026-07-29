"""
Le devoir : ce qui est demandé, quand il peut être rendu, et le recours.

L'enseignant ne pouvait que « préparer des évaluations » — une ligne vide par
étudiant, sans consigne, sans date, sans barème — et rien n'empêchait un dépôt
des mois après la session. Une note publiée, elle, ne se corrigeait plus du
tout : le seul recours passait par la base de données.

Ces cas fixent la fenêtre de dépôt, ce qu'elle refuse, et ce qu'une révision
laisse derrière elle.
"""

from datetime import date, timedelta

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
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
from apps.lms.models import Devoir, Evaluation, RevisionNote

pytestmark = pytest.mark.django_db

MOT_DE_PASSE = "MotDePasseSolide!2026"


# ──────────────────────────────────────────────
# Décor
# ──────────────────────────────────────────────


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


@pytest.fixture
def etudiant(db, cours):
    parcours = Parcours.objects.create(nom="Bachelor", slug="bachelor", type_parcours=Parcours.TypeParcours.LIBRE)
    promotion = Promotion.objects.create(nom="Promotion 2026", parcours=parcours, annee_debut=2026, annee_fin=2029)
    compte = User.objects.create_user(
        username="apprenante",
        email="apprenante@iteag.org",
        password=MOT_DE_PASSE,
        first_name="Léonie",
        last_name="Abaul",
        role=User.Role.ETUDIANT,
    )
    profil = ProfilEtudiant.objects.create(
        utilisateur=compte,
        parcours=parcours,
        promotion=promotion,
        numero_etudiant="ETU-DEV-001",
        statut_inscription=ProfilEtudiant.StatutInscription.ACTIF,
    )
    InscriptionSession.objects.create(etudiant=profil, cours_session=cours)
    return profil


def _devoir(cours, *, ouvre_dans=timedelta(days=-1), ferme_dans=timedelta(days=7), **extra):
    maintenant = timezone.now()
    return Devoir.objects.create(
        cours_session=cours,
        titre="Dissertation sur l'épître aux Romains",
        consigne="Six pages, sources citées.",
        date_ouverture=maintenant + ouvre_dans,
        date_fermeture=maintenant + ferme_dans,
        **extra,
    )


def _fichier():
    return SimpleUploadedFile("copie.pdf", b"%PDF-1.4 contenu", content_type="application/pdf")


# ──────────────────────────────────────────────
# Ouverture du devoir
# ──────────────────────────────────────────────


def test_l_ouverture_cree_une_copie_par_inscrit(cours, etudiant):
    devoir = _devoir(cours)
    services.publier_devoir(devoir)

    assert devoir.statut == Devoir.Statut.PUBLIE
    assert devoir.copies.count() == 1
    copie = devoir.copies.get()
    assert copie.etudiant == etudiant
    assert copie.statut == Evaluation.StatutEvaluation.EN_ATTENTE
    # L'étudiant est averti : un devoir qu'on ignore n'est pas un devoir.
    assert etudiant.utilisateur.notifications.filter(titre__icontains="Nouveau devoir").exists()


def test_l_ouverture_est_idempotente(cours, etudiant):
    devoir = _devoir(cours)
    services.publier_devoir(devoir)
    services.publier_devoir(devoir)
    assert devoir.copies.count() == 1


def test_un_devoir_sans_inscrit_ne_s_ouvre_pas(cours):
    devoir = _devoir(cours)
    with pytest.raises(ValidationError):
        services.publier_devoir(devoir)
    devoir.refresh_from_db()
    assert devoir.statut == Devoir.Statut.BROUILLON


def test_la_fermeture_doit_suivre_l_ouverture(cours):
    devoir = Devoir(
        cours_session=cours,
        titre="Incohérent",
        date_ouverture=timezone.now(),
        date_fermeture=timezone.now() - timedelta(hours=1),
    )
    with pytest.raises(ValidationError):
        devoir.full_clean()


# ──────────────────────────────────────────────
# La fenêtre de dépôt
# ──────────────────────────────────────────────


def test_depot_refuse_avant_l_ouverture(cours, etudiant):
    devoir = _devoir(cours, ouvre_dans=timedelta(days=2), ferme_dans=timedelta(days=9))
    services.publier_devoir(devoir)
    copie = devoir.copies.get()

    assert "ouvre le" in copie.motif_de_refus_depot()
    with pytest.raises(ValidationError):
        services.deposer(copie, _fichier())

    copie.refresh_from_db()
    assert copie.statut == Evaluation.StatutEvaluation.EN_ATTENTE


def test_depot_refuse_apres_la_fermeture(cours, etudiant):
    devoir = _devoir(cours, ouvre_dans=timedelta(days=-10), ferme_dans=timedelta(days=-1))
    devoir.statut = Devoir.Statut.PUBLIE
    devoir.save()
    copie = Evaluation.objects.create(cours_session=cours, etudiant=etudiant, devoir=devoir)

    assert "a fermé le" in copie.motif_de_refus_depot()
    with pytest.raises(ValidationError):
        services.deposer(copie, _fichier())


def test_depot_accepte_dans_la_fenetre(cours, etudiant):
    devoir = _devoir(cours)
    services.publier_devoir(devoir)
    copie = devoir.copies.get()

    services.deposer(copie, _fichier())

    copie.refresh_from_db()
    assert copie.statut == Evaluation.StatutEvaluation.SOUMIS
    assert copie.date_soumission is not None
    assert copie.depot_tardif is False
    assert copie.fichier_soumis


def test_retard_accepte_signale_le_depot_comme_tardif(cours, etudiant):
    """Le devoir reste déposable, mais l'enseignant sait que c'était hors délai."""
    devoir = _devoir(cours, ouvre_dans=timedelta(days=-10), ferme_dans=timedelta(days=-1), retard_accepte=True)
    devoir.statut = Devoir.Statut.PUBLIE
    devoir.save()
    copie = Evaluation.objects.create(cours_session=cours, etudiant=etudiant, devoir=devoir)

    assert copie.motif_de_refus_depot() == ""
    services.deposer(copie, _fichier())

    copie.refresh_from_db()
    assert copie.statut == Evaluation.StatutEvaluation.SOUMIS
    assert copie.depot_tardif is True


def test_un_delai_accorde_prime_sur_la_fermeture(cours, etudiant):
    devoir = _devoir(cours, ouvre_dans=timedelta(days=-10), ferme_dans=timedelta(days=-1))
    devoir.statut = Devoir.Statut.PUBLIE
    devoir.save()
    copie = Evaluation.objects.create(cours_session=cours, etudiant=etudiant, devoir=devoir)

    services.accorder_delai(copie, jusqu_au=timezone.now() + timedelta(days=3))

    copie.refresh_from_db()
    assert copie.motif_de_refus_depot() == ""
    services.deposer(copie, _fichier())
    copie.refresh_from_db()
    assert copie.statut == Evaluation.StatutEvaluation.SOUMIS
    assert copie.depot_tardif is False


def test_un_delai_ne_se_donne_pas_dans_le_passe(cours, etudiant):
    devoir = _devoir(cours)
    services.publier_devoir(devoir)
    with pytest.raises(ValidationError):
        services.accorder_delai(devoir.copies.get(), jusqu_au=timezone.now() - timedelta(hours=1))


def test_une_copie_en_correction_ne_peut_plus_etre_remplacee(cours, etudiant):
    devoir = _devoir(cours)
    services.publier_devoir(devoir)
    copie = devoir.copies.get()
    copie.statut = Evaluation.StatutEvaluation.EN_CORRECTION
    copie.save()

    assert "correction" in copie.motif_de_refus_depot()
    with pytest.raises(ValidationError):
        services.deposer(copie, _fichier())


def test_une_evaluation_hors_devoir_reste_deposable(cours, etudiant):
    """Stages, VAE et saisies du secrétariat n'ont pas de fenêtre à respecter."""
    copie = Evaluation.objects.create(cours_session=cours, etudiant=etudiant)
    assert copie.motif_de_refus_depot() == ""
    services.deposer(copie, _fichier())
    copie.refresh_from_db()
    assert copie.statut == Evaluation.StatutEvaluation.SOUMIS


# ──────────────────────────────────────────────
# Notation et recours
# ──────────────────────────────────────────────


def test_noter_refuse_une_note_deja_publiee(cours, etudiant):
    copie = Evaluation.objects.create(
        cours_session=cours, etudiant=etudiant, statut=Evaluation.StatutEvaluation.PUBLIE, note=12
    )
    with pytest.raises(ValidationError):
        services.noter(copie, note=15)


def test_reviser_conserve_l_ancienne_note_et_avertit(cours, etudiant):
    copie = Evaluation.objects.create(
        cours_session=cours,
        etudiant=etudiant,
        statut=Evaluation.StatutEvaluation.PUBLIE,
        note=9,
        appreciation="Argumentation trop courte.",
    )
    auteur = cours.enseignant.user

    revision = services.reviser(copie, note=13, motif="Recours accordé après seconde lecture.", par=auteur)

    copie.refresh_from_db()
    assert copie.note == 13
    assert copie.statut == Evaluation.StatutEvaluation.PUBLIE  # la note reste publiée
    assert copie.a_ete_revisee is True

    assert revision.note_avant == 9
    assert revision.note_apres == 13
    assert revision.appreciation_avant == "Argumentation trop courte."
    assert revision.auteur == auteur

    assert etudiant.utilisateur.notifications.filter(titre__icontains="Note révisée").exists()


def test_une_revision_sans_motif_est_refusee(cours, etudiant):
    copie = Evaluation.objects.create(
        cours_session=cours, etudiant=etudiant, statut=Evaluation.StatutEvaluation.PUBLIE, note=9
    )
    with pytest.raises(ValidationError):
        services.reviser(copie, note=13, motif="   ")
    assert RevisionNote.objects.count() == 0


def test_on_ne_revise_pas_une_note_non_publiee(cours, etudiant):
    copie = Evaluation.objects.create(
        cours_session=cours, etudiant=etudiant, statut=Evaluation.StatutEvaluation.NOTE, note=9
    )
    with pytest.raises(ValidationError):
        services.reviser(copie, note=13, motif="Erreur de report constatée.")


# ──────────────────────────────────────────────
# Écrans et étanchéité
# ──────────────────────────────────────────────


def test_l_enseignant_voit_ses_devoirs(client, cours, etudiant):
    devoir = _devoir(cours)
    services.publier_devoir(devoir)
    client.force_login(cours.enseignant.user)

    corps = client.get(reverse("lms:devoirs_list")).content.decode()
    # L'apostrophe est échappée par le gabarit : on cherche la partie stable du titre.
    assert "Dissertation sur" in corps
    assert "Romains" in corps


def test_un_enseignant_n_ouvre_pas_le_devoir_d_un_confrere(client, cours, etudiant):
    devoir = _devoir(cours)
    autre_compte = User.objects.create_user(
        username="confrere", email="confrere@iteag.org", password=MOT_DE_PASSE, role=User.Role.ENSEIGNANT
    )
    Professeur.objects.create(nom="Labeth", prenom="Ruth", slug="ruth-labeth", user=autre_compte)
    client.force_login(autre_compte)

    assert client.get(reverse("lms:devoir_detail", args=[devoir.pk])).status_code == 404


def test_l_etudiant_n_atteint_pas_les_ecrans_enseignant(client, cours, etudiant):
    client.force_login(etudiant.utilisateur)
    assert client.get(reverse("lms:devoirs_list")).status_code == 403
    assert client.get(reverse("lms:etudiants_list")).status_code == 403


def test_mes_etudiants_liste_les_inscrits_et_leurs_coordonnees(client, cours, etudiant):
    client.force_login(cours.enseignant.user)
    corps = client.get(reverse("lms:etudiants_list")).content.decode()
    assert "Léonie Abaul" in corps
    assert "apprenante@iteag.org" in corps


def test_le_depot_refuse_s_affiche_sans_404(client, cours, etudiant):
    """Un dépôt hors fenêtre explique pourquoi, au lieu d'une page introuvable."""
    devoir = _devoir(cours, ouvre_dans=timedelta(days=3), ferme_dans=timedelta(days=10))
    services.publier_devoir(devoir)
    copie = devoir.copies.get()

    client.force_login(etudiant.utilisateur)
    reponse = client.get(reverse("etudiant:submit_evaluation", args=[copie.pk]))

    assert reponse.status_code == 200
    assert "Le dépôt ouvre le" in reponse.content.decode()
