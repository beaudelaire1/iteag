"""
Le secrétariat doit pouvoir monter les modules et les ateliers.

L'atelier de production était réservé aux enseignants. Or ce sont eux qui, à
l'ITEAG, ne s'en servent pas : la saisie revient au secrétariat, et elle n'avait
aucune porte. Les modules se créaient donc depuis l'administration Django, ou
pas du tout.

L'invariant à ne pas perdre : **le secrétariat saisit, il ne s'approprie pas.**
Chaque module reste sous la responsabilité d'un enseignant, désigné à la
création. Un module dont le responsable serait une secrétaire deviendrait
orphelin le jour où elle change de poste, et il n'y aurait plus personne à
relancer sur son contenu.
"""

import pytest
from django.urls import reverse

from apps.accounts.models import User
from apps.elearning.models import ModuleFormation
from apps.formations.models import Professeur

pytestmark = pytest.mark.django_db

MOT_DE_PASSE = "motdepasse-long-12"


@pytest.fixture
def enseignant(db):
    compte = User.objects.create_user(
        username="prof_atelier", email="pa@iteag.org", password=MOT_DE_PASSE, role=User.Role.ENSEIGNANT
    )
    return Professeur.objects.create(nom="Nisus", prenom="Alain", slug="nisus-atelier", user=compte)


@pytest.fixture
def autre_enseignant(db):
    compte = User.objects.create_user(
        username="prof_autre", email="pb@iteag.org", password=MOT_DE_PASSE, role=User.Role.ENSEIGNANT
    )
    return Professeur.objects.create(nom="Labeth", prenom="Ruth", slug="labeth-atelier", user=compte)


@pytest.fixture
def secretaire(db):
    return User.objects.create_user(
        username="sec_atelier", email="sa@iteag.org", password=MOT_DE_PASSE, role=User.Role.SECRETARIAT
    )


def saisie(**extra):
    donnees = {
        "titre": "Atelier de prédication — les Psaumes",
        "code": "",
        "description": "",
        "objectifs": "",
        "niveau": "initiation",
        "ects": "0",
        "seuil_completion": "80",
    }
    donnees.update(extra)
    return donnees


class TestAccesDuSecretariat:
    def test_le_secretariat_ouvre_l_atelier(self, client, secretaire):
        client.force_login(secretaire)
        assert client.get(reverse("elearning:enseignant_modules")).status_code == 200

    def test_un_etudiant_reste_dehors(self, client, db):
        etudiant = User.objects.create_user(
            username="etu_atelier", email="ea@iteag.org", password=MOT_DE_PASSE, role=User.Role.ETUDIANT
        )
        client.force_login(etudiant)
        assert client.get(reverse("elearning:enseignant_modules")).status_code in (302, 403)

    def test_le_secretariat_voit_tous_les_modules(self, client, secretaire, enseignant, autre_enseignant):
        """Il saisit pour tout le monde : ne voir personne n'aurait pas de sens."""
        ModuleFormation.objects.create(titre="Christologie", slug="christologie-a", responsable=enseignant)
        ModuleFormation.objects.create(titre="Homilétique", slug="homiletique-a", responsable=autre_enseignant)

        client.force_login(secretaire)
        contenu = client.get(reverse("elearning:enseignant_modules")).content.decode()

        assert "Christologie" in contenu
        assert "Homilétique" in contenu

    def test_un_enseignant_ne_voit_que_les_siens(self, client, enseignant, autre_enseignant):
        ModuleFormation.objects.create(titre="Christologie", slug="christologie-b", responsable=enseignant)
        ModuleFormation.objects.create(titre="Homilétique", slug="homiletique-b", responsable=autre_enseignant)

        client.force_login(enseignant.user)
        contenu = client.get(reverse("elearning:enseignant_modules")).content.decode()

        assert "Christologie" in contenu
        assert "Homilétique" not in contenu


class TestDesignationDuResponsable:
    def test_le_secretariat_choisit_le_responsable(self, client, secretaire, enseignant):
        client.force_login(secretaire)

        reponse = client.post(
            reverse("elearning:enseignant_module_creer"),
            saisie(responsable=enseignant.pk, genre=ModuleFormation.Genre.ATELIER),
        )

        assert reponse.status_code == 302
        module = ModuleFormation.objects.get()
        assert module.responsable == enseignant
        assert module.genre == ModuleFormation.Genre.ATELIER

    def test_le_secretariat_ne_peut_pas_laisser_le_module_sans_responsable(self, client, secretaire):
        """Un module orphelin n'a personne à relancer sur son contenu."""
        client.force_login(secretaire)

        reponse = client.post(reverse("elearning:enseignant_module_creer"), saisie())

        assert reponse.status_code == 200
        assert not ModuleFormation.objects.exists()

    def test_l_enseignant_ne_voit_pas_le_champ_responsable(self, client, enseignant):
        """Le lui montrer lui permettrait de confier son module à un autre."""
        client.force_login(enseignant.user)
        contenu = client.get(reverse("elearning:enseignant_module_creer")).content.decode()

        assert 'name="responsable"' not in contenu

    def test_l_enseignant_reste_responsable_d_office(self, client, enseignant):
        client.force_login(enseignant.user)
        client.post(reverse("elearning:enseignant_module_creer"), saisie(titre="Christologie"))

        assert ModuleFormation.objects.get().responsable == enseignant


class TestNatureDuModule:
    def test_un_module_est_une_formation_par_defaut(self, client, enseignant):
        """Ne pas cocher la nature ne doit pas refuser l'enregistrement."""
        client.force_login(enseignant.user)
        client.post(reverse("elearning:enseignant_module_creer"), saisie(titre="Christologie"))

        assert ModuleFormation.objects.get().genre == ModuleFormation.Genre.FORMATION
