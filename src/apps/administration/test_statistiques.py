"""Tests de la page de statistiques transversale.

Ce qu'on vérifie ici n'est pas « la page répond » mais « les chiffres sont
justes ». Un tableau de bord dont on doute d'un chiffre ne sert plus à rien :
les tests portent donc sur les taux, dont le dénominateur est la première
chose qui se casse, et sur l'absence de fuite vers un compte non habilité.
"""

from datetime import timedelta

import pytest
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
from apps.administration.services import statistiques
from apps.admissions.models import DossierCandidature
from apps.formations.models import Cours, Discipline, Parcours, Professeur


@pytest.fixture
def parcours(db):
    return Parcours.objects.create(
        nom="Théologie", slug="theologie-stats", type_parcours=Parcours.TypeParcours.DIPLOMANT_ITEAG
    )


@pytest.fixture
def promotion(db, parcours):
    return Promotion.objects.create(nom="Promotion stats", parcours=parcours, annee_debut=2025, annee_fin=2031)


@pytest.fixture
def direction(db):
    return User.objects.create_user(
        username="direction_stats",
        email="direction_stats@iteag.org",
        password="motdepasse-long-12",
        role=User.Role.ADMIN,
    )


def _etudiant(parcours, promotion, rang, statut=ProfilEtudiant.StatutInscription.ACTIF):
    utilisateur = User.objects.create_user(
        username=f"etu_stats_{rang}",
        email=f"etu_stats_{rang}@iteag.org",
        password="motdepasse-long-12",
        role=User.Role.ETUDIANT,
    )
    return ProfilEtudiant.objects.create(
        utilisateur=utilisateur,
        parcours=parcours,
        promotion=promotion,
        numero_etudiant=f"STAT-{rang:03d}",
        statut_inscription=statut,
    )


class TestLesTauxNeMententPas:
    def test_un_taux_sans_denominateur_se_rend_par_un_tiret(self, db):
        """« 0 % » se lirait comme un échec ; il n'y a rien à mesurer."""
        assert statistiques._pourcent(0, 0) == "—"
        assert statistiques.admissions().indicateurs[3].valeur == "—"

    def test_le_taux_d_acceptation_ignore_les_dossiers_non_tranches(self, db, parcours):
        for rang, statut in enumerate(
            [
                DossierCandidature.Statut.ACCEPTE,
                DossierCandidature.Statut.REFUSE,
                DossierCandidature.Statut.SOUMIS,
                DossierCandidature.Statut.EN_EXAMEN,
            ]
        ):
            DossierCandidature.objects.create(
                nom=f"Nom{rang}",
                prenom=f"Prenom{rang}",
                email=f"cand{rang}@exemple.org",
                parcours_souhaite=parcours,
                statut=statut,
            )
        domaine = statistiques.admissions()
        indicateurs = {indicateur.libelle: indicateur.valeur for indicateur in domaine.indicateurs}
        assert indicateurs["Dossiers reçus"] == "4"
        assert indicateurs["En cours d'instruction"] == "2"
        # Un accepté sur deux dossiers tranchés, et non un sur quatre.
        assert indicateurs["Taux d'acceptation"] == "50\u00a0%"

    def test_le_remplissage_rapporte_les_inscrits_aux_places_ouvertes(self, db, parcours, promotion):
        aujourd_hui = timezone.localdate()
        session = SessionAcademique.objects.create(
            nom="Session test",
            annee_academique="2025-2026",
            date_debut=aujourd_hui,
            date_fin=aujourd_hui + timedelta(days=90),
        )
        cours = Cours.objects.create(
            titre="Introduction",
            slug="introduction-stats",
            discipline=Discipline.objects.create(nom="Exégèse", slug="exegese-stats"),
        )
        enseignant = Professeur.objects.create(nom="Kuen", prenom="Alfred", slug="kuen-stats")
        offre = CoursDeSession.objects.create(cours=cours, session=session, enseignant=enseignant, capacite=10)
        for rang in range(2):
            InscriptionSession.objects.create(etudiant=_etudiant(parcours, promotion, rang), cours_session=offre)

        indicateurs = {i.libelle: i for i in statistiques.scolarite().indicateurs}
        assert indicateurs["Remplissage des cours"].valeur == "20\u00a0%"
        assert "10" in indicateurs["Remplissage des cours"].precision


class TestLaSerieCouvreDouzeMoisPleins:
    def test_les_mois_sans_activite_restent_visibles(self, db, parcours):
        DossierCandidature.objects.create(
            nom="Récent",
            prenom="Dossier",
            email="recent@exemple.org",
            parcours_souhaite=parcours,
        )
        serie = statistiques.admissions().serie
        assert len(serie) == 12
        # Le mois courant est le dernier, et il porte le dossier créé à l'instant.
        assert serie[-1].texte == "1"
        assert serie[0].texte == "0"

    def test_la_barre_la_plus_haute_occupe_toute_la_largeur(self, db):
        barres = statistiques._barres([("a", 1), ("b", 4), ("c", 0)])
        assert [barre.part for barre in barres] == [25, 100, 0]


class TestLaPageEstReserveeALaDirection:
    def test_la_direction_voit_toutes_les_applications(self, client, direction):
        client.force_login(direction)
        reponse = client.get(reverse("administration:statistiques"))
        assert reponse.status_code == 200
        cles = {domaine.cle for domaine in reponse.context["domaines"]}
        assert cles == {
            "admissions",
            "scolarite",
            "enseignement",
            "formation_video",
            "bibliotheque",
            "comptes",
        }

    def test_un_etudiant_n_atteint_pas_les_chiffres_de_l_institut(self, client, db, parcours, promotion):
        client.force_login(_etudiant(parcours, promotion, 90).utilisateur)
        reponse = client.get(reverse("administration:statistiques"))
        assert reponse.status_code in (302, 403)

    def test_la_page_tient_debout_sans_aucune_donnee(self, client, direction):
        """Une base vide est l'état du premier jour : la page doit s'afficher."""
        client.force_login(direction)
        reponse = client.get(reverse("administration:statistiques"))
        assert reponse.status_code == 200
        assert "Statistiques de l'institut" in reponse.content.decode()
