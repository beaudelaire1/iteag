"""
Périmètre du secrétariat — la doctrine de partage, vérifiée.

L'ITEAG compte quatre personnes hors enseignants. Traiter le secrétariat comme
un rôle diminué crée des impasses quotidiennes : quelqu'un doit interrompre la
direction pour un acte courant. Mais l'ouvrir sans limite ferait disparaître la
séparation qui protège les actes coûteux.

La ligne retenue ne porte pas sur l'importance de l'écran mais sur la nature du
pouvoir qu'il confère. Ce fichier en est l'énoncé exécutable : chaque ligne du
tableau est un cas, et la table **est** la spécification.
"""

import pytest
from django.urls import reverse

from apps.accounts.models import User

# Écrans que le secrétariat doit pouvoir ouvrir : l'opérationnel.
OPERATIONNEL = [
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
    ("library:gestion", "tenir le fonds documentaire"),
    ("commerce:gestion_commandes", "traiter les commandes de livres"),
    ("commerce:gestion_stock", "tenir le stock de livres"),
]

# Écrans réservés à la direction : donner des droits, engager, détruire.
REGALIEN = [
    ("administration:utilisateurs", "créer des comptes donne des droits"),
    ("administration:user_create", "créer des comptes donne des droits"),
    # Décision explicite de la maîtrise d'ouvrage, pas une conséquence de la
    # doctrine : la validation des acquis reste un acte de direction.
    ("administration:vae", "la maîtrise d'ouvrage réserve la VAE à la direction"),
    ("administration:vae_create", "la maîtrise d'ouvrage réserve la VAE à la direction"),
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
@pytest.mark.parametrize(("nom_url", "raison"), OPERATIONNEL, ids=[nom for nom, _ in OPERATIONNEL])
def test_le_secretariat_accede_a_l_operationnel(client, secretaire, nom_url, raison):
    client.force_login(secretaire)
    reponse = client.get(reverse(nom_url))
    assert reponse.status_code == 200, f"Le secrétariat doit pouvoir {raison} ({nom_url})."


@pytest.mark.django_db
@pytest.mark.parametrize(("nom_url", "raison"), REGALIEN, ids=[nom for nom, _ in REGALIEN])
def test_le_secretariat_est_tenu_hors_du_regalien(client, secretaire, nom_url, raison):
    client.force_login(secretaire)
    reponse = client.get(reverse(nom_url))
    assert reponse.status_code in (302, 403), f"Écran réservé à la direction : {raison} ({nom_url})."


@pytest.mark.django_db
@pytest.mark.parametrize(("nom_url", "_raison"), OPERATIONNEL + REGALIEN, ids=[n for n, _ in OPERATIONNEL + REGALIEN])
def test_la_direction_accede_a_tout(client, directrice, nom_url, _raison):
    client.force_login(directrice)
    assert client.get(reverse(nom_url)).status_code == 200


@pytest.mark.django_db
def test_les_suppressions_restent_a_la_direction(client, secretaire, db):
    """Une suppression est irréversible : elle ne se délègue pas."""
    from apps.formations.models import Discipline, Professeur

    professeur = Professeur.objects.create(nom="Témoin", prenom="Cas", slug="cas-temoin", user=None)
    Discipline.objects.create(nom="Discipline témoin", slug="discipline-temoin")

    client.force_login(secretaire)
    reponse = client.get(reverse("administration:professeur_delete", args=[professeur.pk]))
    assert reponse.status_code in (302, 403)
    assert Professeur.objects.filter(pk=professeur.pk).exists()


@pytest.mark.django_db
def test_la_grille_tarifaire_ne_se_modifie_pas_au_secretariat(client, secretaire):
    """Consulter les tarifs est opérationnel ; les fixer engage l'institut."""
    client.force_login(secretaire)
    assert client.get(reverse("administration:tarifs")).status_code == 200
    assert client.get(reverse("administration:tarif_create")).status_code in (302, 403)


@pytest.mark.django_db
def test_un_enseignant_n_entre_pas_dans_le_back_office(client, db):
    enseignant = User.objects.create_user(
        username="ens_perimetre", email="e@iteag.org", password="motdepasse-long-12", role=User.Role.ENSEIGNANT
    )
    client.force_login(enseignant)
    for nom_url, _ in OPERATIONNEL:
        assert client.get(reverse(nom_url)).status_code in (302, 403), nom_url
