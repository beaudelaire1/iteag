"""Garde-fous spécifiques à la dernière recette avant bascule publique."""

from pathlib import Path

import pytest
from django.test import override_settings
from django.urls import reverse

RACINE = Path(__file__).resolve().parents[2]


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("ancienne", "nouvelle"),
    [
        ("/presentation", "/presentation/"),
        ("/education", "/formations/"),
        ("/diploma", "/formations/parcours/diplomant-iteag/"),
        ("/educationinministry", "/formations/parcours/iteag-pro/"),
        ("/enroll", "/admissions/candidature/"),
        (
            "/formations/parcours/parcours-diplomant-iteag/",
            "/formations/parcours/diplomant-iteag/",
        ),
        (
            "/formations/parcours/parcours-bachelor-flte/",
            "/formations/parcours/bachelor-flte/",
        ),
    ],
)
def test_anciennes_urls_publiques_redirigent_en_301(client, ancienne, nouvelle):
    reponse = client.get(f"{ancienne}?utm_source=ancien-site")

    assert reponse.status_code == 301
    assert reponse["Location"] == f"{nouvelle}?utm_source=ancien-site"


def test_footer_utilise_les_slugs_de_reference():
    footer = (RACINE / "templates" / "partials" / "footer.html").read_text(encoding="utf-8")

    assert "/formations/parcours/diplomant-iteag/" in footer
    assert "/formations/parcours/bachelor-flte/" in footer
    assert "/formations/parcours/parcours-diplomant-iteag/" not in footer
    assert "/formations/parcours/parcours-bachelor-flte/" not in footer


@override_settings(ALLOWED_HOSTS=["iteag-preprod.137.74.169.188.sslip.io", "iteag.org", "www.iteag.org"])
def test_preproduction_est_non_indexable(client):
    reponse = client.get(
        "/robots.txt",
        HTTP_HOST="iteag-preprod.137.74.169.188.sslip.io",
    )

    assert reponse.status_code == 200
    assert reponse["X-Robots-Tag"] == "noindex, nofollow, noarchive"


@override_settings(ALLOWED_HOSTS=["iteag.org", "www.iteag.org"])
def test_domaine_public_reste_indexable(client):
    reponse = client.get("/robots.txt", HTTP_HOST="iteag.org")

    assert reponse.status_code == 200
    assert "X-Robots-Tag" not in reponse.headers


@pytest.mark.django_db
def test_newsletter_refuse_un_retour_vers_un_domaine_externe(client):
    reponse = client.post(
        reverse("core:newsletter_inscription"),
        {"email": "invalide", "suivant": "https://example.org/piege"},
    )

    assert reponse.status_code == 302
    assert reponse["Location"] == "/"
