"""Filtres combinables de la liste des comptes utilisateurs."""
from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User

pytestmark = pytest.mark.django_db


@pytest.fixture
def comptes_filtres(client):
    responsable = User.objects.create_user(
        username="responsable_filtres",
        email="responsable@example.org",
        password="motdepasse-long-12",
        role=User.Role.ADMIN,
        is_staff=True,
    )
    client.force_login(responsable)

    donnees = [
        ("actif_recent", User.Role.ETUDIANT, True, 2),
        ("actif_jamais", User.Role.ETUDIANT, True, None),
        ("inactif_ancien", User.Role.ETUDIANT, False, 60),
        ("inactif_jamais", User.Role.ENSEIGNANT, False, None),
    ]
    for nom, role, actif, jours in donnees:
        compte = User.objects.create_user(
            username=nom,
            email=f"{nom}@example.org",
            password="motdepasse-long-12",
            role=role,
            is_active=actif,
        )
        if jours is not None:
            compte.last_login = timezone.now() - timedelta(days=jours)
            compte.save(update_fields=["last_login"])


@pytest.mark.parametrize(
    ("filtres", "attendus"),
    [
        ({"statut": "actif"}, {"actif_recent", "actif_jamais"}),
        ({"statut": "inactif"}, {"inactif_ancien"}),
        ({"connexion": "jamais"}, {"actif_jamais"}),
        ({"connexion": "deja"}, {"actif_recent", "inactif_ancien"}),
        ({"connexion": "7j"}, {"actif_recent"}),
        ({"connexion": "30j"}, {"actif_recent"}),
        ({"connexion": "plus_30j"}, {"inactif_ancien"}),
        (
            {"statut": "inactif", "connexion": "plus_30j", "q": "ancien"},
            {"inactif_ancien"},
        ),
        (
            {"statut": "inconnu", "connexion": "inconnue"},
            {"actif_recent", "actif_jamais", "inactif_ancien"},
        ),
    ],
)
def test_filtres_combinables(client, comptes_filtres, filtres, attendus):
    reponse = client.get(reverse("administration:utilisateurs"), {"role": "etudiant", **filtres})
    assert reponse.status_code == 200
    assert {compte.username for compte in reponse.context["users"]} == attendus
    assert reponse.context["current_statut"] == (
        filtres.get("statut") if filtres.get("statut") in ("actif", "inactif") else ""
    )
    assert reponse.context["current_connexion"] == (
        filtres.get("connexion")
        if filtres.get("connexion") in ("jamais", "deja", "7j", "30j", "plus_30j")
        else ""
    )


def test_la_pagination_conserve_tous_les_filtres(client, comptes_filtres):
    User.objects.bulk_create(
        [
            User(
                username=f"pagination_cible_{i}",
                email=f"pagination_{i}@example.org",
                role=User.Role.ETUDIANT,
                is_active=False,
            )
            for i in range(35)
        ]
    )
    url = reverse("administration:utilisateurs")
    params = {
        "q": "pagination_cible",
        "role": "etudiant",
        "statut": "inactif",
        "connexion": "jamais",
    }
    reponse = client.get(url, params)
    assert reponse.status_code == 200
    assert reponse.context["users"].paginator.count == 35
    html = reponse.content.decode()
    assert "page=2" in html
    for parametre in ("q=pagination_cible", "role=etudiant", "statut=inactif", "connexion=jamais"):
        assert parametre in html

    seconde_page = client.get(url, {**params, "page": 2})
    assert seconde_page.status_code == 200
    assert len(seconde_page.context["users"]) == 5
