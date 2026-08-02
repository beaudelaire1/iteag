"""Un devoir peut viser un groupe, une promotion ou des étudiants désignés.

Il ne s'adressait qu'à tout le cours. Un travail de groupe, un rattrapage pour
un seul étudiant ou un sujet propre à une promotion se donnaient donc hors de
la plateforme, et rien n'en était suivi.

L'invariant à ne pas perdre : la cible **restreint** toujours les inscrits, elle
ne les élargit jamais. Désigner une promotion entière ne donne pas le devoir à
qui ne suit pas le cours — cela lui créerait une copie qu'il n'attend pas.
"""

from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
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
from apps.lms.models import Devoir, Evaluation, GroupeEtudiants
from apps.lms.services import publier_devoir

pytestmark = pytest.mark.django_db

MOT_DE_PASSE = "motdepasse-long-12"


@pytest.fixture
def parcours(db):
    return Parcours.objects.create(nom="Bachelor", slug="bach-dest", type_parcours=Parcours.TypeParcours.LIBRE)


@pytest.fixture
def promotions(db, parcours):
    return (
        Promotion.objects.create(nom="Promo A", parcours=parcours, annee_debut=2026, annee_fin=2029),
        Promotion.objects.create(nom="Promo B", parcours=parcours, annee_debut=2027, annee_fin=2030),
    )


@pytest.fixture
def offre(db):
    compte = User.objects.create_user(
        username="prof_dest", email="pd@iteag.org", password=MOT_DE_PASSE, role=User.Role.ENSEIGNANT
    )
    professeur = Professeur.objects.create(nom="Nisus", prenom="Alain", slug="nisus-dest", user=compte)
    discipline = Discipline.objects.create(nom="Théologie", slug="theo-dest")
    cours = Cours.objects.create(titre="Herméneutique", slug="herm-dest", discipline=discipline)
    aujourd_hui = timezone.localdate()
    session = SessionAcademique.objects.create(
        nom="Session", date_debut=aujourd_hui - timedelta(days=5), date_fin=aujourd_hui + timedelta(days=25)
    )
    return CoursDeSession.objects.create(session=session, cours=cours, enseignant=professeur)


def _etudiant(parcours, promotion, suffixe, inscrit_a=None):
    compte = User.objects.create_user(
        username=f"etu-{suffixe}", email=f"{suffixe}@iteag.org", password=MOT_DE_PASSE, role=User.Role.ETUDIANT
    )
    profil = ProfilEtudiant.objects.create(
        utilisateur=compte, parcours=parcours, promotion=promotion, numero_etudiant=f"ETU2026{suffixe}"
    )
    if inscrit_a is not None:
        InscriptionSession.objects.create(etudiant=profil, cours_session=inscrit_a)
    return profil


def _devoir(offre, **extra):
    maintenant = timezone.now()
    return Devoir.objects.create(
        cours_session=offre,
        titre="Dissertation",
        date_ouverture=maintenant - timedelta(hours=1),
        date_fermeture=maintenant + timedelta(days=7),
        **extra,
    )


def _copies(devoir):
    return set(Evaluation.objects.filter(devoir=devoir).values_list("etudiant__numero_etudiant", flat=True))


class TestPorteeDuDevoir:
    def test_par_defaut_tous_les_inscrits(self, offre, parcours, promotions):
        promo_a, _ = promotions
        _etudiant(parcours, promo_a, "901", inscrit_a=offre)
        _etudiant(parcours, promo_a, "902", inscrit_a=offre)

        devoir = _devoir(offre)
        publier_devoir(devoir)

        assert _copies(devoir) == {"ETU2026901", "ETU2026902"}

    def test_un_groupe_restreint_aux_membres(self, offre, parcours, promotions):
        promo_a, _ = promotions
        membre = _etudiant(parcours, promo_a, "903", inscrit_a=offre)
        _etudiant(parcours, promo_a, "904", inscrit_a=offre)

        groupe = GroupeEtudiants.objects.create(cours_session=offre, nom="Projet Romains")
        groupe.membres.add(membre)

        devoir = _devoir(offre, portee=Devoir.Portee.GROUPE, groupe=groupe)
        publier_devoir(devoir)

        assert _copies(devoir) == {"ETU2026903"}

    def test_une_promotion_restreint_a_ses_etudiants(self, offre, parcours, promotions):
        promo_a, promo_b = promotions
        _etudiant(parcours, promo_a, "905", inscrit_a=offre)
        _etudiant(parcours, promo_b, "906", inscrit_a=offre)

        devoir = _devoir(offre, portee=Devoir.Portee.PROMOTION, promotion=promo_a)
        publier_devoir(devoir)

        assert _copies(devoir) == {"ETU2026905"}

    def test_des_etudiants_designes(self, offre, parcours, promotions):
        promo_a, _ = promotions
        vise = _etudiant(parcours, promo_a, "907", inscrit_a=offre)
        _etudiant(parcours, promo_a, "908", inscrit_a=offre)

        devoir = _devoir(offre, portee=Devoir.Portee.ETUDIANTS)
        devoir.etudiants.add(vise)
        publier_devoir(devoir)

        assert _copies(devoir) == {"ETU2026907"}

    def test_une_promotion_n_atteint_pas_les_non_inscrits(self, offre, parcours, promotions):
        """L'invariant : la cible restreint les inscrits, elle ne les élargit pas."""
        promo_a, _ = promotions
        _etudiant(parcours, promo_a, "909", inscrit_a=offre)
        _etudiant(parcours, promo_a, "910")  # même promotion, mais ne suit pas ce cours

        devoir = _devoir(offre, portee=Devoir.Portee.PROMOTION, promotion=promo_a)
        publier_devoir(devoir)

        assert _copies(devoir) == {"ETU2026909"}

    def test_une_cible_sans_inscrit_refuse_la_publication(self, offre, parcours, promotions):
        """Publier pour personne laisserait un devoir ouvert que nul ne voit."""
        promo_a, promo_b = promotions
        _etudiant(parcours, promo_a, "911", inscrit_a=offre)

        devoir = _devoir(offre, portee=Devoir.Portee.PROMOTION, promotion=promo_b)
        with pytest.raises(ValidationError, match="aucun destinataire"):
            publier_devoir(devoir)

        devoir.refresh_from_db()
        assert devoir.statut == Devoir.Statut.BROUILLON


class TestValidation:
    def test_une_portee_groupe_exige_un_groupe(self, offre):
        devoir = _devoir(offre, portee=Devoir.Portee.GROUPE)
        with pytest.raises(ValidationError):
            devoir.full_clean()

    def test_une_portee_promotion_exige_une_promotion(self, offre):
        devoir = _devoir(offre, portee=Devoir.Portee.PROMOTION)
        with pytest.raises(ValidationError):
            devoir.full_clean()

    def test_un_groupe_d_un_autre_cours_est_refuse(self, offre, db):
        """Un groupe appartient à son cours : l'emprunter viserait d'autres inscrits."""
        autre_cours = Cours.objects.create(titre="Patristique", slug="patr-dest", discipline=offre.cours.discipline)
        autre_offre = CoursDeSession.objects.create(
            session=offre.session, cours=autre_cours, enseignant=offre.enseignant
        )
        groupe_etranger = GroupeEtudiants.objects.create(cours_session=autre_offre, nom="Ailleurs")

        devoir = _devoir(offre, portee=Devoir.Portee.GROUPE, groupe=groupe_etranger)
        with pytest.raises(ValidationError):
            devoir.full_clean()


class TestLibelle:
    def test_le_libelle_dit_la_cible(self, offre, parcours, promotions):
        promo_a, _ = promotions
        groupe = GroupeEtudiants.objects.create(cours_session=offre, nom="Projet Romains")

        assert _devoir(offre).libelle_destinataires == "Tous les inscrits au cours"
        assert "Projet Romains" in _devoir(offre, portee=Devoir.Portee.GROUPE, groupe=groupe).libelle_destinataires
        assert "Promo A" in _devoir(offre, portee=Devoir.Portee.PROMOTION, promotion=promo_a).libelle_destinataires
