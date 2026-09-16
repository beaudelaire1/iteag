"""L'onglet porte l'emblème de l'ITEAG, et /favicon.ico y mène."""

from pathlib import Path

from django.conf import settings
from django.test import Client, override_settings

ICONES = (
    "img/favicon-32.png",
    "img/favicon-192.png",
    "img/favicon-512.png",
    "img/apple-touch-icon.png",
    "img/favicon.ico",
)


def test_les_fichiers_d_icone_existent():
    statique = Path(settings.BASE_DIR) / "static"
    assert [icone for icone in ICONES if not (statique / icone).exists()] == []


@override_settings(STATIC_URL="/static/")
def test_le_gabarit_declare_l_emblème_et_non_plus_la_lettre():
    gabarit = (Path(settings.BASE_DIR) / "templates" / "base.html").read_text(encoding="utf-8")
    assert "img/favicon-32.png" in gabarit
    assert "apple-touch-icon.png" in gabarit
    assert "favicon.svg" not in gabarit


def test_favicon_ico_redirige_vers_le_fichier_statique(db):
    reponse = Client().get("/favicon.ico")
    assert reponse.status_code == 302
    assert reponse["Location"].endswith("img/favicon.ico")
