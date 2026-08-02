"""Ce que le secrétariat a le droit d'ouvrir doit être atteignable depuis sa barre.

Le partage des rôles lui-même est énoncé dans « test_perimetre.py », et il
n'est pas remis en cause ici : toute la gestion au secrétariat, le pilotage à
la direction.

Le défaut corrigé est ailleurs, et plus banal : **des écrans que le
secrétariat avait déjà le droit d'ouvrir ne figuraient pas dans sa barre**, et
n'étaient atteignables qu'en devinant leur adresse. Un droit sans chemin pour
l'exercer n'existe pas dans les faits.
"""

import pytest
from django.urls import reverse

from apps.accounts.models import User

pytestmark = pytest.mark.django_db

MOT_DE_PASSE = "motdepasse-long-12"

# Les écrans qui manquaient à la barre, alors que les vues les autorisaient.
REVELES = [
    ("administration:professeurs", "tenir les fiches enseignants"),
    ("administration:formations", "consulter l'offre de parcours"),
    ("administration:tarifs", "consulter la grille tarifaire"),
    ("library:gestion", "tenir le fonds documentaire"),
    ("administration:vae", "instruire les validations d'acquis"),
    ("administration:utilisateurs", "tenir les comptes"),
]

# Réservé à la direction : la barre ne doit pas y mener non plus.
RESERVES = [
    ("administration:dashboard", "le pilotage n'est pas la scolarité"),
]


@pytest.fixture
def secretaire(db):
    return User.objects.create_user(
        username="sec_barre", email="sb@iteag.org", password=MOT_DE_PASSE, role=User.Role.SECRETARIAT
    )


@pytest.fixture
def barre(client, secretaire):
    client.force_login(secretaire)
    return client.get(reverse("secretariat:dashboard")).content.decode()


def _lien(route: str) -> str:
    """L'attribut complet, et non le chemin seul.

    « /espace-admin/ » est le préfixe de toutes les adresses du back-office :
    le chercher tel quel ferait passer n'importe quelle entrée pour un lien
    vers le tableau de bord.
    """
    return f'href="{reverse(route)}"'


@pytest.mark.parametrize(("route", "raison"), REVELES, ids=[nom for nom, _ in REVELES])
def test_la_barre_mene_aux_ecrans_autorises(barre, route, raison):
    assert _lien(route) in barre, f"Le secrétariat doit pouvoir {raison} sans deviner l'adresse ({route})."


@pytest.mark.parametrize(("route", "raison"), RESERVES, ids=[nom for nom, _ in RESERVES])
def test_la_barre_ne_mene_pas_au_pilotage(barre, route, raison):
    assert _lien(route) not in barre, f"Écran réservé à la direction : {raison} ({route})."


@pytest.mark.parametrize(("route", "raison"), REVELES, ids=[nom for nom, _ in REVELES])
def test_les_ecrans_reveles_repondent_bien(client, secretaire, route, raison):
    """Rendre un écran atteignable ne sert à rien s'il refuse le rôle."""
    client.force_login(secretaire)
    assert client.get(reverse(route)).status_code == 200


def test_la_barre_de_bureau_et_le_menu_mobile_disent_la_meme_chose(barre):
    """Deux barres qui divergent créent deux périmètres selon l'appareil."""
    for route, _ in REVELES:
        assert barre.count(_lien(route)) >= 2, f"{route} doit figurer dans la barre latérale et dans le menu mobile"
