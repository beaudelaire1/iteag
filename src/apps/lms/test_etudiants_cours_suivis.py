"""La liste des étudiants doit dire dans quels cours ils sont inscrits.

Elle ne montrait que le nom, la promotion et les coordonnées : l'enseignant qui
assure trois cours ne savait pas, en la lisant, lequel chaque étudiant suivait.

Le périmètre est volontairement restreint à *ses* cours. La scolarité complète
d'un étudiant relève du secrétariat ; un enseignant n'a pas à savoir ce que son
étudiant suit ailleurs pour animer le sien.
"""

from datetime import timedelta

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
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

pytestmark = pytest.mark.django_db

MOT_DE_PASSE = "motdepasse-long-12"


@pytest.fixture
def session_courante(db):
    aujourd_hui = timezone.localdate()
    return SessionAcademique.objects.create(
        nom="Session en cours",
        date_debut=aujourd_hui - timedelta(days=10),
        date_fin=aujourd_hui + timedelta(days=20),
    )


@pytest.fixture
def enseignant(db):
    compte = User.objects.create_user(
        username="prof_liste", email="pl@iteag.org", password=MOT_DE_PASSE, role=User.Role.ENSEIGNANT
    )
    return Professeur.objects.create(nom="Nisus", prenom="Alain", slug="nisus-liste", user=compte)


@pytest.fixture
def discipline(db):
    return Discipline.objects.create(nom="Théologie", slug="theo-liste")


def _cours(discipline, session, enseignant, titre, slug):
    cours = Cours.objects.create(titre=titre, slug=slug, discipline=discipline)
    return CoursDeSession.objects.create(session=session, cours=cours, enseignant=enseignant)


@pytest.fixture
def etudiant(db):
    parcours = Parcours.objects.create(nom="Bachelor", slug="bach-liste", type_parcours=Parcours.TypeParcours.LIBRE)
    promotion = Promotion.objects.create(nom="Promo liste", parcours=parcours, annee_debut=2026, annee_fin=2029)
    compte = User.objects.create_user(
        username="etu_liste", email="el@iteag.org", password=MOT_DE_PASSE, role=User.Role.ETUDIANT
    )
    return ProfilEtudiant.objects.create(
        utilisateur=compte, parcours=parcours, promotion=promotion, numero_etudiant="ETU2026801"
    )


def test_la_liste_montre_les_cours_suivis(client, enseignant, discipline, session_courante, etudiant):
    offre = _cours(discipline, session_courante, enseignant, "Herméneutique", "hermeneutique-liste")
    InscriptionSession.objects.create(etudiant=etudiant, cours_session=offre)

    client.force_login(enseignant.user)
    contenu = client.get(reverse("lms:etudiants_list")).content.decode()

    assert "Herméneutique" in contenu
    assert "Mes cours suivis" in contenu


def test_seuls_les_cours_de_cet_enseignant_paraissent(client, enseignant, discipline, session_courante, etudiant, db):
    """La scolarité complète relève du secrétariat, pas de cet écran."""
    le_mien = _cours(discipline, session_courante, enseignant, "Herméneutique", "herm-mien")
    autre_compte = User.objects.create_user(
        username="autre_prof", email="ap@iteag.org", password=MOT_DE_PASSE, role=User.Role.ENSEIGNANT
    )
    autre_prof = Professeur.objects.create(nom="Autre", prenom="Prof", slug="autre-liste", user=autre_compte)
    celui_d_un_autre = _cours(discipline, session_courante, autre_prof, "Patristique", "patristique-liste")

    InscriptionSession.objects.create(etudiant=etudiant, cours_session=le_mien)
    InscriptionSession.objects.create(etudiant=etudiant, cours_session=celui_d_un_autre)

    client.force_login(enseignant.user)
    contenu = client.get(reverse("lms:etudiants_list")).content.decode()

    assert "Herméneutique" in contenu
    assert "Patristique" not in contenu, "Le cours d'un collègue n'a pas à figurer ici"


def test_les_cours_sont_precharges_en_une_requete(client, enseignant, discipline, session_courante, db):
    """Une requête par étudiant ferait croître la page avec l'effectif."""
    parcours = Parcours.objects.create(nom="P", slug="p-n1", type_parcours=Parcours.TypeParcours.LIBRE)
    promotion = Promotion.objects.create(nom="Pr", parcours=parcours, annee_debut=2026, annee_fin=2029)
    offre = _cours(discipline, session_courante, enseignant, "Herméneutique", "herm-n1")
    rang = iter(range(1000))

    def inscrire(nombre):
        for _ in range(nombre):
            index = next(rang)
            compte = User.objects.create_user(
                username=f"etu-n{index}", email=f"e{index}@x.org", password=MOT_DE_PASSE, role=User.Role.ETUDIANT
            )
            profil = ProfilEtudiant.objects.create(
                utilisateur=compte, parcours=parcours, promotion=promotion, numero_etudiant=f"ETU2026{index:04d}"
            )
            InscriptionSession.objects.create(etudiant=profil, cours_session=offre)

    client.force_login(enseignant.user)

    inscrire(2)
    with CaptureQueriesContext(connection) as petit:
        client.get(reverse("lms:etudiants_list"))

    inscrire(10)
    with CaptureQueriesContext(connection) as grand:
        client.get(reverse("lms:etudiants_list"))

    assert len(grand) - len(petit) <= 2, (
        f"{len(petit)} requêtes pour 2 étudiants, {len(grand)} pour 12 : le préchargement ne joue pas"
    )
