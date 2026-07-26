"""Fixtures du domaine e-learning."""

import pytest

from apps.academics.models import ProfilEtudiant, Promotion
from apps.accounts.models import User
from apps.elearning.models import Chapitre, Lecon, ModuleFormation, VideoAsset
from apps.formations.models import Discipline, Parcours, Professeur


@pytest.fixture
def parcours(db):
    return Parcours.objects.create(
        nom="Parcours diplômant ITEAG",
        slug="diplomant-iteag",
        type_parcours=Parcours.TypeParcours.DIPLOMANT_ITEAG,
        ects_requis=180,
    )


@pytest.fixture
def promotion(db, parcours):
    return Promotion.objects.create(nom="Promotion 2024-2030", parcours=parcours, annee_debut=2024, annee_fin=2030)


@pytest.fixture
def discipline(db):
    return Discipline.objects.create(nom="Théologie systématique", slug="theologie-systematique")


@pytest.fixture
def utilisateur_etudiant(db):
    return User.objects.create_user(
        username="marie",
        email="marie@iteag.org",
        password="motdepasse-long-12",
        first_name="Marie",
        last_name="Durand",
        role=User.Role.ETUDIANT,
    )


@pytest.fixture
def profil(db, utilisateur_etudiant, parcours, promotion):
    return ProfilEtudiant.objects.create(
        utilisateur=utilisateur_etudiant,
        parcours=parcours,
        promotion=promotion,
        numero_etudiant="ETU-2024-001",
        statut_inscription=ProfilEtudiant.StatutInscription.ACTIF,
    )


@pytest.fixture
def enseignant(db):
    utilisateur = User.objects.create_user(
        username="prof",
        email="prof@iteag.org",
        password="motdepasse-long-12",
        role=User.Role.ENSEIGNANT,
    )
    return Professeur.objects.create(user=utilisateur, nom="Nisus", prenom="Alain", slug="alain-nisus")


@pytest.fixture
def secretaire(db):
    return User.objects.create_user(
        username="secretaire",
        email="secretaire@iteag.org",
        password="motdepasse-long-12",
        role=User.Role.SECRETARIAT,
    )


@pytest.fixture
def video_prete(db):
    return VideoAsset.objects.create(
        titre="Introduction",
        cle_stockage="videos/test-introduction.mp4",
        # Référence historique explicite : les nouvelles vidéos passent
        # exclusivement par un fournisseur externe.
        fournisseur="local",
        duree_secondes=600,
        statut_traitement=VideoAsset.StatutTraitement.PRET,
    )


@pytest.fixture
def module(db, discipline, enseignant):
    """Module publié, réservé aux inscrits du parcours."""
    return ModuleFormation.objects.create(
        titre="Christologie",
        slug="christologie",
        discipline=discipline,
        responsable=enseignant,
        statut=ModuleFormation.StatutPublication.PUBLIE,
        politique_acces=ModuleFormation.PolitiqueAcces.INSCRIT_PARCOURS,
        seuil_completion=80,
    )


@pytest.fixture
def chapitre(db, module):
    return Chapitre.objects.create(module=module, titre="Fondements", ordre=1)


@pytest.fixture
def lecon(db, chapitre, video_prete):
    """Leçon vidéo standard, protégée."""
    return Lecon.objects.create(
        chapitre=chapitre,
        titre="La personne du Christ",
        slug="personne-du-christ",
        type_lecon=Lecon.TypeLecon.VIDEO,
        video=video_prete,
        ordre=1,
        duree_secondes=600,
    )


@pytest.fixture
def lecon_apercu(db, chapitre, video_prete):
    return Lecon.objects.create(
        chapitre=chapitre,
        titre="Présentation du module",
        slug="presentation",
        type_lecon=Lecon.TypeLecon.VIDEO,
        video=video_prete,
        ordre=2,
        duree_secondes=120,
        apercu_gratuit=True,
        obligatoire=False,
    )


@pytest.fixture
def acces(db, profil, module):
    from apps.elearning.services.octroi import octroyer

    return octroyer(profil, module, notifier_etudiant=False)
