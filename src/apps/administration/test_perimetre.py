"""
Périmètre du secrétariat — la doctrine de partage, vérifiée.

L'ITEAG compte quatre personnes hors enseignants. La maîtrise d'ouvrage a
tranché : le secrétariat tient l'ensemble des écrans de gestion, y compris les
suppressions, les tarifs et les comptes. Seul le pilotage — tableaux de bord de
direction et administration Django avancée — lui reste fermé.

Deux garde-fous demeurent, et ils ne tiennent pas au rôle mais au formulaire :
le secrétariat ne peut ni s'attribuer le rôle d'administrateur, ni toucher à un
compte de direction. Ce fichier en est l'énoncé exécutable.
"""

import pytest
from django.urls import reverse

from apps.accounts.models import User

# Écrans que le secrétariat doit pouvoir ouvrir : toute la gestion.
GESTION = [
    ("administration:candidatures", "instruire les dossiers"),
    ("administration:etudiants", "tenir le fichier étudiant"),
    ("administration:professeurs", "tenir les fiches enseignants"),
    ("administration:formations", "consulter l'offre"),
    ("administration:courses", "tenir le référentiel des cours"),
    ("administration:sessions", "programmer les sessions"),
    ("administration:course_offerings", "programmer les cours"),
    ("administration:enrollment_requests", "traiter les inscriptions"),
    ("administration:promotions", "gérer les promotions"),
    ("administration:stages", "suivre les stages"),
    ("administration:credits_ects", "porter les crédits"),
    ("administration:payments", "encaisser"),
    ("administration:tarifs", "consulter la grille"),
    ("administration:tarif_create", "fixer un tarif"),
    ("administration:vae", "instruire les validations d'acquis"),
    ("administration:vae_create", "enregistrer une validation d'acquis"),
    ("administration:utilisateurs", "tenir les comptes"),
    ("administration:user_create", "ouvrir un compte"),
    ("library:gestion", "tenir le fonds documentaire"),
]

# Écrans réservés à la direction : le pilotage.
PILOTAGE = [
    ("administration:dashboard", "les indicateurs de direction restent à la direction"),
]


@pytest.fixture
def secretaire(db):
    return User.objects.create_user(
        username="sec_perimetre",
        email="sec@iteag.org",
        password="motdepasse-long-12",
        role=User.Role.SECRETARIAT,
    )


@pytest.fixture
def directrice(db):
    return User.objects.create_user(
        username="dir_perimetre",
        email="dir@iteag.org",
        password="motdepasse-long-12",
        role=User.Role.ADMIN,
    )


@pytest.mark.django_db
@pytest.mark.parametrize(("nom_url", "raison"), GESTION, ids=[nom for nom, _ in GESTION])
def test_le_secretariat_accede_a_toute_la_gestion(client, secretaire, nom_url, raison):
    client.force_login(secretaire)
    reponse = client.get(reverse(nom_url))
    assert reponse.status_code == 200, f"Le secrétariat doit pouvoir {raison} ({nom_url})."


@pytest.mark.django_db
@pytest.mark.parametrize(("nom_url", "raison"), PILOTAGE, ids=[nom for nom, _ in PILOTAGE])
def test_le_secretariat_est_tenu_hors_du_pilotage(client, secretaire, nom_url, raison):
    client.force_login(secretaire)
    reponse = client.get(reverse(nom_url))
    assert reponse.status_code in (302, 403), f"Écran réservé à la direction : {raison} ({nom_url})."


@pytest.mark.django_db
@pytest.mark.parametrize(("nom_url", "_raison"), GESTION + PILOTAGE, ids=[n for n, _ in GESTION + PILOTAGE])
def test_la_direction_accede_a_tout(client, directrice, nom_url, _raison):
    client.force_login(directrice)
    assert client.get(reverse(nom_url)).status_code == 200


@pytest.mark.django_db
def test_les_suppressions_sont_ouvertes_au_secretariat(client, secretaire, db):
    """Quatre personnes : attendre la direction pour une correction bloque le travail."""
    from apps.formations.models import Discipline, Professeur

    professeur = Professeur.objects.create(nom="Témoin", prenom="Cas", slug="cas-temoin", user=None)
    Discipline.objects.create(nom="Discipline témoin", slug="discipline-temoin")

    client.force_login(secretaire)
    reponse = client.get(reverse("administration:professeur_delete", args=[professeur.pk]))
    assert reponse.status_code == 200


@pytest.mark.django_db
def test_le_secretariat_ne_se_hisse_pas_a_la_direction(client, secretaire):
    """Sans ce garde-fou, la séparation des rôles ne serait qu'un affichage."""
    client.force_login(secretaire)
    reponse = client.post(
        reverse("administration:user_create"),
        {
            "username": "tentative",
            "first_name": "",
            "last_name": "",
            "email": "tentative@iteag.org",
            "phone": "",
            "role": User.Role.ADMIN,
            "is_active": "on",
            "password1": "motdepasse-long-12",
        },
    )
    assert reponse.status_code == 200
    assert not User.objects.filter(username="tentative").exists()


@pytest.mark.django_db
def test_le_secretariat_ne_modifie_pas_un_compte_de_direction(client, secretaire, directrice):
    client.force_login(secretaire)
    reponse = client.post(
        reverse("administration:user_update", args=[directrice.pk]),
        {
            "username": directrice.username,
            "first_name": "Détournée",
            "last_name": "",
            "email": directrice.email,
            "phone": "",
            "role": User.Role.SECRETARIAT,
            "is_active": "on",
        },
    )
    assert reponse.status_code == 200
    directrice.refresh_from_db()
    assert directrice.role == User.Role.ADMIN


@pytest.mark.django_db
def test_la_grille_tarifaire_se_modifie_au_secretariat(client, secretaire):
    client.force_login(secretaire)
    assert client.get(reverse("administration:tarifs")).status_code == 200
    assert client.get(reverse("administration:tarif_create")).status_code == 200


@pytest.mark.django_db
def test_un_enseignant_n_entre_pas_dans_le_back_office(client, db):
    enseignant = User.objects.create_user(
        username="ens_perimetre", email="e@iteag.org", password="motdepasse-long-12", role=User.Role.ENSEIGNANT
    )
    client.force_login(enseignant)
    for nom_url, _ in GESTION + PILOTAGE:
        assert client.get(reverse(nom_url)).status_code in (302, 403), nom_url
