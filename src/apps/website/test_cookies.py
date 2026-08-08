from pathlib import Path

import pytest
from django.conf import settings
from django.urls import reverse

from apps.website.sitemaps import PagesPubliquesSitemap


@pytest.mark.django_db
def test_politique_cookies_est_publique(client):
    reponse = client.get(reverse("website:politique_cookies"))

    assert reponse.status_code == 200
    contenu = reponse.content.decode("utf-8")
    assert "Politique des cookies" in contenu
    assert "sessionid" in contenu
    assert "csrftoken" in contenu
    assert "iteag_cookie_consent" in contenu
    assert "iteag_video_quality" in contenu
    assert "Bunny.net" in contenu
    assert "aucun cookie publicitaire" in contenu


def test_politique_cookies_est_dans_le_sitemap_public():
    assert "website:politique_cookies" in PagesPubliquesSitemap().items()


def test_socle_charge_le_bandeau_et_son_gestionnaire():
    templates = Path(settings.BASE_DIR) / "templates"
    base = (templates / "base.html").read_text(encoding="utf-8")
    footer = (templates / "partials" / "footer.html").read_text(encoding="utf-8")
    bandeau = (templates / "partials" / "bandeau_cookies.html").read_text(encoding="utf-8")
    script = (Path(settings.BASE_DIR) / "static" / "js" / "consentement-cookies.js").read_text(encoding="utf-8")

    assert "partials/bandeau_cookies.html" in base
    assert "consentement-cookies.js" in base
    assert "data-cookie-settings" in footer
    assert "Essentiels uniquement" in bandeau
    assert "Accepter les préférences" in bandeau
    assert "iteag_cookie_consent" in script
    assert "allows: autorise" in script
    assert "SameSite=Lax" in script
    assert 'CLES_PREFERENCES_LOCALES = ["iteag_video_quality"]' in script
    assert "supprimerPreferencesLocales" in script


def test_aucun_outil_de_mesure_n_est_annonce_comme_actif():
    politique = (Path(settings.BASE_DIR) / "templates" / "website" / "politique_cookies.html").read_text(
        encoding="utf-8"
    )

    assert "Aucun outil de mesure d'audience" in politique
    assert "aucune régie publicitaire" in politique
