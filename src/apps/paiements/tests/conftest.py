from decimal import Decimal

import pytest

from apps.academics.models import ProfilEtudiant, Promotion
from apps.accounts.models import User
from apps.elearning.models import Chapitre, Lecon, ModuleFormation, VideoAsset
from apps.formations.models import Discipline, Parcours, Professeur
from apps.paiements.models import Reglement


@pytest.fixture(autouse=True)
def _stripe(settings):
    settings.STRIPE_CLE_SECRETE = "sk_test_pour_les_tests"
    settings.STRIPE_SECRET_WEBHOOK = "whsec_pour_les_tests"
    settings.STRIPE_CLE_PUBLIABLE = "pk_test_pour_les_tests"
    settings.BUNNY_ZONE_DIFFUSION = "https://vz-test.b-cdn.net"
    settings.BUNNY_CLE_SIGNATURE = "cle-de-test"


@pytest.fixture
def professeur(db):
    utilisateur = User.objects.create_user(
        username="prof_paiement",
        email="prof@iteag.org",
        password="motdepasse-long-12",
        role=User.Role.ENSEIGNANT,
    )
    return Professeur.objects.create(user=utilisateur, nom="Nestor", prenom="Marie", slug="marie-nestor")


@pytest.fixture
def module_vendu(db, professeur):
    """Un module publié, vendu 120 € TTC, avec une leçon protégée et un aperçu."""
    module = ModuleFormation.objects.create(
        titre="Théologie systématique",
        slug="theologie-systematique",
        discipline=Discipline.objects.create(nom="Dogmatique", slug="dogmatique"),
        responsable=professeur,
        statut=ModuleFormation.StatutPublication.PUBLIE,
        politique_acces=ModuleFormation.PolitiqueAcces.ACHAT,
        prix_ttc=Decimal("120.00"),
        taux_tva=Decimal("0.00"),
    )
    chapitre = Chapitre.objects.create(module=module, titre="Ouverture", ordre=1)
    video = VideoAsset.objects.create(
        titre="Leçon 1",
        cle_stockage="cle-theologie-1",
        fournisseur="bunny",
        uploade_par=professeur.user,
        statut_traitement=VideoAsset.StatutTraitement.PRET,
    )
    Lecon.objects.create(chapitre=chapitre, titre="Introduction", slug="introduction", ordre=1, video=video)
    return module


@pytest.fixture
def etudiant(db):
    parcours = Parcours.objects.create(
        nom="Licence", slug="licence-paiement", type_parcours=Parcours.TypeParcours.DIPLOMANT_ITEAG
    )
    promotion = Promotion.objects.create(nom="Promo 2030", parcours=parcours, annee_debut=2029, annee_fin=2032)
    utilisateur = User.objects.create_user(
        username="etudiant_paiement",
        email="etudiant@iteag.org",
        password="motdepasse-long-12",
        role=User.Role.ETUDIANT,
    )
    return ProfilEtudiant.objects.create(
        utilisateur=utilisateur,
        parcours=parcours,
        promotion=promotion,
        numero_etudiant="ETU-PAIE-1",
        statut_inscription=ProfilEtudiant.StatutInscription.ACTIF,
    )


@pytest.fixture
def reglement(db, module_vendu, etudiant):
    return Reglement.objects.create(
        nature=Reglement.Nature.MODULE,
        module=module_vendu,
        etudiant=etudiant,
        utilisateur=etudiant.utilisateur,
        email=etudiant.utilisateur.email,
        libelle=f"Formation — {module_vendu.titre}",
        montant_ttc=Decimal("120.00"),
        taux_tva=Decimal("0.00"),
        session_stripe="cs_test_123",
    )


def evenement(type_evenement, objet, identifiant="evt_test_1"):
    """Notification Stripe minimale, telle que `construct_event` la renvoie."""
    return {"id": identifiant, "type": type_evenement, "data": {"object": objet}}
