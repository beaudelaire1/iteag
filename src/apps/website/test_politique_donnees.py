from pathlib import Path

import pytest
from django.conf import settings
from django.urls import reverse

from apps.website.sitemaps import PagesPubliquesSitemap


@pytest.mark.django_db
def test_politique_donnees_est_publique(client):
    reponse = client.get(reverse("website:politique_donnees"))

    assert reponse.status_code == 200
    contenu = reponse.content.decode("utf-8")
    assert "Protection des données personnelles" in contenu
    assert "Responsable du traitement" in contenu
    assert "Vos droits" in contenu
    assert "Durées de conservation" in contenu
    assert "Commission nationale de l'informatique et des libertés" in contenu


def test_politique_donnees_est_dans_le_sitemap_public():
    assert "website:politique_donnees" in PagesPubliquesSitemap().items()


def test_politique_couvre_les_traitements_reellement_presents():
    source = (Path(settings.BASE_DIR) / "templates" / "website" / "politique_donnees.html").read_text(encoding="utf-8")

    for attendu in (
        "Candidatures",
        "Comptes, scolarité et activités pédagogiques",
        "Bibliothèque",
        "Boutique, règlements et facturation",
        "Stripe",
        "Cloudflare",
        "Bunny.net",
        "Sentry",
    ):
        assert attendu in source


def test_les_formulaires_principaux_informent_sur_les_donnees():
    templates = Path(settings.BASE_DIR) / "templates"
    candidature = (templates / "admissions" / "candidature_form.html").read_text(encoding="utf-8")
    commande = (templates / "commerce" / "commander.html").read_text(encoding="utf-8")
    footer = (templates / "partials" / "footer.html").read_text(encoding="utf-8")

    assert "partials/information_donnees.html" in candidature
    assert "partials/information_donnees.html" in commande
    assert "website:politique_donnees" in footer
    assert "Votre adresse est utilisée uniquement pour cette lettre d'information" in footer


def test_le_registre_interne_documente_les_durees_du_cahier_des_charges():
    chemin_registre = Path(settings.BASE_DIR).parent / "docs" / "conformite" / "registre_traitements.md"
    registre = chemin_registre.read_text(encoding="utf-8")

    assert "refus : 2 ans" in registre
    assert "cursus + 5 ans" in registre
    assert "12 mois" in registre
    assert "10 ans" in registre
    assert "candidatures refusées" in registre
    assert "fichiers dans R2" in registre
