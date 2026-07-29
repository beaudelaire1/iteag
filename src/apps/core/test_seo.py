"""Le référencement ne doit ni oublier le catalogue public, ni indexer des brouillons."""

import json
import re

import pytest
from django.contrib.sitemaps.views import sitemap
from django.template.loader import render_to_string
from django.test import RequestFactory, override_settings

from apps.commerce.models import ProduitLivre
from apps.core.context_processors import site_context
from apps.core.sitemaps import (
    CoursSitemap,
    LivresBoutiqueSitemap,
    ModulesPubliesSitemap,
    NoticesBibliothequeSitemap,
    PagesPubliquesSitemap,
    ParcoursSitemap,
    ProfesseursSitemap,
)
from apps.elearning.models import ModuleFormation
from apps.formations.models import Cours, Discipline, Parcours, Professeur
from apps.library.models import NoticeBibliographique


@override_settings(SITE_URL="https://iteag.org")
def test_robots_indique_un_seul_groupe_et_le_sitemap(client):
    contenu = client.get("/robots.txt").content.decode()

    assert contenu.count("User-agent: *") == 1
    assert "Disallow: /admin/" in contenu
    assert "Disallow: /django-admin/" in contenu
    assert "Sitemap: https://iteag.org/sitemap.xml" in contenu


@override_settings(SITE_URL="https://iteag.org")
def test_url_canonique_ignore_les_parametres_de_filtrage():
    requete = RequestFactory().get("/formations/?page=2&tri=nom")

    assert site_context(requete)["CANONICAL_URL"] == "https://iteag.org/formations/"


@override_settings(STATIC_URL="/static/")
def test_schema_organisation_est_un_json_valide():
    contexte = {
        "SITE_URL": "https://iteag.org",
        "SITE_NAME": "ITEAG",
        "SITE_FULL_NAME": "Institut de Théologie Évangélique des Antilles et de la Guyane",
        "SITE_PHONE": "+590 690 37 64 17",
        "SITE_EMAIL": "secretariat@iteag.org",
        "SITE_FACEBOOK": "https://fr-fr.facebook.com/iteag",
        "SITE_YOUTUBE": "https://www.youtube.com/@formationiteag327",
    }
    rendu = render_to_string("partials/jsonld_organization.html", contexte)
    donnees = [json.loads(bloc) for bloc in re.findall(r"<script[^>]*>(.*?)</script>", rendu, re.S)]
    organisation = next(bloc for bloc in donnees if bloc["@type"] == "EducationalOrganization")
    site = next(bloc for bloc in donnees if bloc["@type"] == "WebSite")

    assert organisation["@id"] == "https://iteag.org/#organization"
    assert {zone["name"] for zone in organisation["areaServed"]} == {"Guadeloupe", "Martinique", "Guyane"}
    assert site["name"] == "ITEAG"
    assert site["url"] == "https://iteag.org/"


@pytest.mark.django_db
@override_settings(ALLOWED_HOSTS=["iteag.org", "testserver"])
def test_sitemap_xml_couvre_tous_les_catalogues_publics():
    discipline = Discipline.objects.create(nom="Théologie", slug="theologie")
    parcours = Parcours.objects.create(
        nom="Parcours public",
        slug="parcours-public",
        type_parcours=Parcours.TypeParcours.LIBRE,
        actif=True,
    )
    parcours_inactif = Parcours.objects.create(
        nom="Parcours retiré",
        slug="parcours-retire",
        type_parcours=Parcours.TypeParcours.LIBRE,
        actif=False,
    )
    cours = Cours.objects.create(titre="Cours public", slug="cours-public", discipline=discipline, actif=True)
    cours_inactif = Cours.objects.create(
        titre="Cours retiré",
        slug="cours-retire",
        discipline=discipline,
        actif=False,
    )
    professeur = Professeur.objects.create(nom="Public", prenom="Professeur", slug="professeur-public", actif=True)
    professeur_inactif = Professeur.objects.create(
        nom="Retiré",
        prenom="Professeur",
        slug="professeur-retire",
        actif=False,
    )
    module = ModuleFormation.objects.create(
        titre="Module public",
        slug="module-public",
        statut=ModuleFormation.StatutPublication.PUBLIE,
    )
    module_brouillon = ModuleFormation.objects.create(
        titre="Module brouillon",
        slug="module-brouillon",
        statut=ModuleFormation.StatutPublication.BROUILLON,
    )
    notice = NoticeBibliographique.objects.create(titre="Ouvrage public")
    livre = ProduitLivre.objects.create(
        titre="Livre public",
        slug="livre-public",
        sku="SEO-LIVRE-1",
        prix_ttc="20.00",
        actif=True,
    )
    livre_inactif = ProduitLivre.objects.create(
        titre="Livre retiré",
        slug="livre-retire",
        sku="SEO-LIVRE-2",
        prix_ttc="20.00",
        actif=False,
    )

    requete = RequestFactory().get("/sitemap.xml", secure=True, HTTP_HOST="iteag.org")
    reponse = sitemap(
        requete,
        {
            "pages-publiques": PagesPubliquesSitemap,
            "parcours": ParcoursSitemap,
            "cours": CoursSitemap,
            "professeurs": ProfesseursSitemap,
            "modules": ModulesPubliesSitemap,
            "bibliotheque": NoticesBibliothequeSitemap,
            "boutique": LivresBoutiqueSitemap,
        },
    )
    reponse.render()
    urls = {element.decode() for element in re.findall(rb"<loc>([^<]+)</loc>", reponse.content)}

    attendues = {
        "https://iteag.org/formations/",
        "https://iteag.org/formations/professeurs/",
        "https://iteag.org/e-learning/",
        "https://iteag.org/bibliotheque/",
        "https://iteag.org/boutique/",
        f"https://iteag.org{parcours.get_absolute_url()}",
        f"https://iteag.org{cours.get_absolute_url()}",
        f"https://iteag.org{professeur.get_absolute_url()}",
        f"https://iteag.org{module.get_absolute_url()}",
        f"https://iteag.org/bibliotheque/notice/{notice.pk}/",
        f"https://iteag.org{livre.get_absolute_url()}",
    }
    exclues = {
        f"https://iteag.org{parcours_inactif.get_absolute_url()}",
        f"https://iteag.org{cours_inactif.get_absolute_url()}",
        f"https://iteag.org{professeur_inactif.get_absolute_url()}",
        f"https://iteag.org{module_brouillon.get_absolute_url()}",
        f"https://iteag.org{livre_inactif.get_absolute_url()}",
    }

    assert attendues <= urls
    assert urls.isdisjoint(exclues)
