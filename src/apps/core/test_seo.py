"""Le référencement ne doit ni oublier le catalogue public, ni indexer des brouillons."""

import json
import re
from datetime import UTC, datetime
from pathlib import Path

import pytest
from django.conf import settings
from django.contrib.sitemaps.views import sitemap
from django.template.loader import render_to_string
from django.test import RequestFactory, override_settings

from apps.core.context_processors import site_context
from apps.core.templatetags.iteag_tags import absolute_url
from apps.elearning.models import ModuleFormation
from apps.formations.models import Cours, Discipline, Parcours, Professeur
from apps.library.models import NoticeBibliographique
from apps.website.models_publications import TemoignageEtudiant
from apps.website.sitemaps import (
    CoursSitemap,
    ModulesPubliesSitemap,
    NoticesBibliothequeSitemap,
    PagesPubliquesSitemap,
    ParcoursSitemap,
    ProfesseursSitemap,
    TemoignagesPubliesSitemap,
)


@override_settings(SITE_URL="https://iteag.org")
def test_robots_indique_un_seul_groupe_et_le_sitemap(client):
    contenu = client.get("/robots.txt").content.decode()

    assert contenu.count("User-agent: *") == 1
    assert "Disallow: /admin/" in contenu
    assert "Disallow: /django-admin/" in contenu
    assert "Sitemap: https://iteag.org/sitemap.xml" in contenu


@override_settings(SITE_URL="https://iteag.org")
def test_url_canonique_ignore_les_parametres_de_filtrage():
    requete = RequestFactory().get("/formations/?tri=nom")

    assert site_context(requete)["CANONICAL_URL"] == "https://iteag.org/formations/"


@override_settings(SITE_URL="https://iteag.org", ALLOWED_HOSTS=["iteag.org"])
def test_url_canonique_conserve_la_pagination():
    requete = RequestFactory().get("/articles/?page=2&q=theologie", HTTP_HOST="iteag.org")

    contexte = site_context(requete)

    assert contexte["CANONICAL_URL"] == "https://iteag.org/articles/?page=2"
    assert contexte["SEO_ROBOTS"] == "noindex, follow"


def test_url_image_absolue_accepte_un_stockage_local_ou_externe():
    assert absolute_url("/media/image.jpg", "https://iteag.org") == "https://iteag.org/media/image.jpg"
    assert absolute_url("https://cdn.example/image.jpg", "https://iteag.org") == "https://cdn.example/image.jpg"


@override_settings(STATIC_URL="/static/")
def test_apercu_social_global_couvre_open_graph_et_x():
    rendu = render_to_string(
        "partials/social_meta.html",
        {
            "SITE_URL": "https://iteag.org",
            "SITE_NAME": "ITEAG",
            "SITE_TAGLINE": "Formation théologique",
            "CANONICAL_URL": "https://iteag.org/formations/",
            "social_title": "Formations — ITEAG",
            "social_description": "Les formations de l'ITEAG.",
        },
    )

    assert 'property="og:locale" content="fr_FR"' in rendu
    assert 'name="twitter:card" content="summary_large_image"' in rendu
    assert 'property="og:image" content="https://iteag.org/static/img/og-iteag.png"' in rendu
    assert 'name="twitter:image" content="https://iteag.org/static/img/og-iteag.png"' in rendu


def test_schema_article_est_un_json_valide_sans_image():
    rendu = render_to_string(
        "partials/jsonld_article.html",
        {
            "SITE_URL": "https://iteag.org",
            "SITE_FULL_NAME": "Institut de Théologie Évangélique des Antilles et de la Guyane",
            "CANONICAL_URL": "https://iteag.org/articles/exemple/",
            "headline": "Une lecture de l'épître aux Romains",
            "description": "Un article de recherche.",
            "date_published": datetime(2026, 9, 2, tzinfo=UTC),
            "date_modified": datetime(2026, 9, 2, tzinfo=UTC),
            "author": "Marie Exemple",
        },
    )
    donnees = json.loads(re.search(r"<script[^>]*>(.*?)</script>", rendu, re.S).group(1))

    assert donnees["@type"] == "Article"
    assert donnees["headline"] == "Une lecture de l'épître aux Romains"
    assert donnees["author"]["name"] == "Marie Exemple"
    assert "image" not in donnees


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


CONTEXTE_SITE = {
    "SITE_URL": "https://iteag.org",
    "SITE_FULL_NAME": "Institut de Théologie Évangélique des Antilles et de la Guyane",
    "CANONICAL_URL": "https://iteag.org/formations/exemple/",
}


def _course(**parametres):
    rendu = render_to_string("partials/jsonld_course.html", CONTEXTE_SITE | parametres)
    bloc = re.search(r"<script[^>]*>(.*?)</script>", rendu, re.S).group(1)
    # Un JSON invalide n'est pas une erreur visible : le moteur de recherche
    # ignore le bloc en silence, et la fiche disparaît des résultats enrichis
    # sans que rien ne le signale. D'où le parsage réel plutôt qu'une
    # recherche de sous-chaîne.
    return json.loads(bloc)


class TestDonneesStructureesDesFormations:
    """
    Le même gabarit sert aux cours, aux parcours et aux modules e-learning.
    Les champs facultatifs y sont introduits par des virgules conditionnelles :
    c'est exactement la construction qui produit un JSON invalide au premier
    remaniement, et qui échoue sans bruit.
    """

    def test_le_minimum_suffit_a_produire_un_json_valide(self):
        donnees = _course(nom="Introduction à l'Ancien Testament")

        assert donnees["@type"] == "Course"
        assert donnees["name"] == "Introduction à l'Ancien Testament"
        assert donnees["provider"]["@id"] == "https://iteag.org/#organization"
        assert donnees["inLanguage"] == "fr"
        # Les champs non fournis ne doivent pas apparaître vides.
        assert "educationalLevel" not in donnees
        assert "instructor" not in donnees
        assert "courseMode" not in donnees

    def test_tous_les_champs_facultatifs_ensemble_restent_valides(self):
        donnees = _course(
            nom="Module e-learning",
            description="<p>Une description <strong>balisée</strong>.</p>",
            credential="180 ECTS",
            niveau="Licence",
            instructeur="Marie Nestor",
            mode="online",
        )

        assert donnees["educationalCredentialAwarded"] == "180 ECTS"
        assert donnees["educationalLevel"] == "Licence"
        assert donnees["instructor"] == {"@type": "Person", "name": "Marie Nestor"}
        assert donnees["courseMode"] == "online"
        assert "<p>" not in donnees["description"]

    def test_une_apostrophe_ne_casse_pas_le_bloc(self):
        """Le nom d'un parcours en contient presque toujours une."""
        donnees = _course(nom="Théologie « pratique » de l'Église", description='Guillemets "droits" inclus.')

        assert "Église" in donnees["name"]

    @pytest.mark.parametrize(
        ("gabarit", "attendu"),
        [
            ("formations/cours_detail.html", "cours"),
            ("formations/parcours_detail.html", "parcours"),
            ("elearning/module_detail.html", "module"),
        ],
    )
    def test_les_trois_fiches_emploient_le_meme_gabarit(self, gabarit, attendu):
        """
        Le module portait sa propre copie du bloc. Deux descriptions du même
        type d'objet finissent par diverger : celle qu'on oublie de corriger
        est celle que le moteur de recherche lit.
        """
        chemin = Path(settings.BASE_DIR) / "templates" / gabarit
        source = chemin.read_text(encoding="utf-8")
        assert "partials/jsonld_course.html" in source
        assert '"@type": "Course"' not in source, f"La fiche {attendu} redéfinit le bloc au lieu de l'inclure."


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
    temoignage = TemoignageEtudiant.objects.create(
        nom_affiche="Étudiante ITEAG",
        texte="Une formation qui m'a fait grandir.",
        consentement_publication=True,
        statut=TemoignageEtudiant.Statut.PUBLIE,
    )
    TemoignageEtudiant.objects.create(
        nom_affiche="Témoignage privé",
        texte="Ne pas publier.",
        consentement_publication=False,
        statut=TemoignageEtudiant.Statut.PUBLIE,
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
            "temoignages": TemoignagesPubliesSitemap,
        },
    )
    reponse.render()
    urls = {element.decode() for element in re.findall(rb"<loc>([^<]+)</loc>", reponse.content)}

    attendues = {
        "https://iteag.org/formations/",
        "https://iteag.org/formations/professeurs/",
        "https://iteag.org/e-learning/",
        "https://iteag.org/bibliotheque/",
        "https://iteag.org/articles/",
        "https://iteag.org/admissions/candidature/",
        f"https://iteag.org{parcours.get_absolute_url()}",
        f"https://iteag.org{cours.get_absolute_url()}",
        f"https://iteag.org{professeur.get_absolute_url()}",
        f"https://iteag.org{module.get_absolute_url()}",
        f"https://iteag.org/bibliotheque/notice/{notice.pk}/",
        f"https://iteag.org/temoignages/{temoignage.pk}/",
    }
    exclues = {
        f"https://iteag.org{parcours_inactif.get_absolute_url()}",
        f"https://iteag.org{cours_inactif.get_absolute_url()}",
        f"https://iteag.org{professeur_inactif.get_absolute_url()}",
        f"https://iteag.org{module_brouillon.get_absolute_url()}",
    }

    assert attendues <= urls
    assert urls.isdisjoint(exclues)
