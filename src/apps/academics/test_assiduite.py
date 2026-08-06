from datetime import date, time, timedelta

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse

from apps.academics.models import (
    CoursDeSession,
    InscriptionSession,
    ProfilEtudiant,
    Promotion,
    SessionAcademique,
)
from apps.academics.models_assiduite import HistoriquePresence, Presence, SeanceCours
from apps.academics.services_assiduite import enregistrer_presence
from apps.accounts.models import User
from apps.formations.models import Cours, Discipline, Parcours, Professeur


@pytest.fixture
def univers_assiduite(db):
    parcours = Parcours.objects.create(
        nom="Parcours assiduité",
        slug="parcours-assiduite",
        type_parcours=Parcours.TypeParcours.DIPLOMANT_ITEAG,
    )
    promotion = Promotion.objects.create(
        nom="Promotion assiduité",
        parcours=parcours,
        annee_debut=2026,
        annee_fin=2032,
    )
    discipline = Discipline.objects.create(nom="Assiduité", slug="assiduite")
    cours = Cours.objects.create(titre="Cours de démonstration", slug="cours-assiduite", discipline=discipline)
    cours.parcours.add(parcours)

    enseignant_user = User.objects.create_user(
        username="enseignant_assiduite",
        password="mot-de-passe-solide",
        role=User.Role.ENSEIGNANT,
    )
    professeur = Professeur.objects.create(
        user=enseignant_user,
        nom="Professeur",
        prenom="Anne",
        slug="anne-professeur",
    )
    debut = date.today()
    session = SessionAcademique.objects.create(
        nom="Session assiduité",
        periode=SessionAcademique.Periode.JUILLET,
        annee_academique="2026-2027",
        date_debut=debut,
        date_fin=debut + timedelta(days=7),
    )
    offre = CoursDeSession.objects.create(
        session=session,
        cours=cours,
        enseignant=professeur,
    )

    etudiant_user = User.objects.create_user(
        username="etudiant_assiduite",
        password="mot-de-passe-solide",
        role=User.Role.ETUDIANT,
        first_name="Noémie",
        last_name="Test",
    )
    etudiant = ProfilEtudiant.objects.create(
        utilisateur=etudiant_user,
        parcours=parcours,
        promotion=promotion,
        numero_etudiant="26000001",
        statut_inscription=ProfilEtudiant.StatutInscription.ACTIF,
    )
    InscriptionSession.objects.create(etudiant=etudiant, cours_session=offre)

    admin = User.objects.create_user(
        username="admin_assiduite",
        password="mot-de-passe-solide",
        role=User.Role.ADMIN,
    )
    return {
        "offre": offre,
        "etudiant": etudiant,
        "enseignant": enseignant_user,
        "admin": admin,
        "session": session,
    }


@pytest.mark.django_db
def test_seance_refuse_une_date_hors_session(univers_assiduite):
    seance = SeanceCours(
        cours_session=univers_assiduite["offre"],
        date=univers_assiduite["session"].date_fin + timedelta(days=1),
        heure_debut=time(8, 0),
        heure_fin=time(12, 0),
    )
    with pytest.raises(ValidationError):
        seance.full_clean()


@pytest.mark.django_db
def test_correction_presence_est_tracee(univers_assiduite):
    seance = SeanceCours.objects.create(
        cours_session=univers_assiduite["offre"],
        date=univers_assiduite["session"].date_debut,
        heure_debut=time(8, 0),
        heure_fin=time(12, 0),
        cree_par=univers_assiduite["admin"],
    )
    enregistrer_presence(
        seance=seance,
        etudiant=univers_assiduite["etudiant"],
        statut=Presence.Statut.PRESENT,
        commentaire="",
        auteur=univers_assiduite["admin"],
    )
    enregistrer_presence(
        seance=seance,
        etudiant=univers_assiduite["etudiant"],
        statut=Presence.Statut.RETARD,
        commentaire="Arrivée à 8 h 20",
        auteur=univers_assiduite["admin"],
    )
    presence = Presence.objects.get(seance=seance, etudiant=univers_assiduite["etudiant"])
    assert presence.statut == Presence.Statut.RETARD
    historique = HistoriquePresence.objects.get(presence=presence)
    assert historique.ancien_statut == Presence.Statut.PRESENT
    assert historique.nouveau_statut == Presence.Statut.RETARD


@pytest.mark.django_db
def test_administrateur_cree_une_seance_depuis_le_portail(client, univers_assiduite):
    client.force_login(univers_assiduite["admin"])
    reponse = client.post(
        reverse("administration:assiduite_cours", kwargs={"pk": univers_assiduite["offre"].pk}),
        {
            "date": univers_assiduite["session"].date_debut.isoformat(),
            "heure_debut": "08:00",
            "heure_fin": "12:00",
            "libelle": "Matin",
        },
    )
    assert reponse.status_code == 302
    assert SeanceCours.objects.filter(cours_session=univers_assiduite["offre"]).count() == 1


@pytest.mark.django_db
def test_enseignant_ne_voit_que_son_cours(client, univers_assiduite):
    client.force_login(univers_assiduite["enseignant"])
    reponse = client.get(reverse("administration:assiduite"))
    assert reponse.status_code == 200
    assert list(reponse.context["offres"]) == [univers_assiduite["offre"]]
