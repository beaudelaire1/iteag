"""Garde-fous spécifiques à la dernière recette avant bascule publique."""

from pathlib import Path

import pytest
from django.contrib.auth import get_user_model
from django.template.loader import get_template
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


def test_footer_garde_une_hierarchie_de_titres_et_un_contraste_lisibles():
    footer = (RACINE / "templates" / "partials" / "footer.html").read_text(encoding="utf-8")

    assert '<h3 class="overline-light' not in footer
    assert footer.count('<h2 class="overline-light') == 3
    assert 'class="text-xs text-warm-600"' not in footer


def test_composants_de_petit_texte_passent_par_le_pipeline_css():
    production = (RACINE / "assets" / "css" / "production.css").read_text(encoding="utf-8")
    css = (RACINE / "assets" / "css" / "accessibilite-couleurs.css").read_text(encoding="utf-8")
    package = (RACINE / "package.json").read_text(encoding="utf-8")

    assert '@import "./input.css";' in production
    assert '@import "./accessibilite-couleurs.css";' in production
    assert "assets/css/production.css" in package
    assert ".overline" in css and "--color-gold-700" in css
    assert ".stat-label" in css and "--color-warm-600" in css


def test_accueil_rend_les_blocs_editoriaux_generiques():
    template = (RACINE / "templates" / "website" / "home_page.html").read_text(encoding="utf-8")

    assert "{% include_block block %}" in template
    # Vérifie également que la syntaxe Django/Wagtail reste compilable après
    # l'ajout du fallback générique.
    assert get_template("website/home_page.html") is not None


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
def test_reponse_authentifiee_ne_peut_pas_etre_mise_en_cache_partage(client):
    utilisateur = get_user_model().objects.create_user(
        username="cache-test",
        email="cache-test@example.org",
        password="MotDePasseDeTest123!",
    )
    client.force_login(utilisateur)

    reponse = client.get(reverse("core:notifications"))
    directives = {item.strip().lower() for item in reponse.headers["Cache-Control"].split(",")}

    assert reponse.status_code == 200
    assert {"private", "no-cache", "no-store", "must-revalidate"} <= directives


@pytest.mark.django_db
def test_newsletter_refuse_un_retour_vers_un_domaine_externe(client):
    reponse = client.post(
        reverse("core:newsletter_inscription"),
        {"email": "invalide", "suivant": "https://example.org/piege"},
    )

    assert reponse.status_code == 302
    assert reponse["Location"] == "/"
