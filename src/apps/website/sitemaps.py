"""Sitemaps des contenus publics qui ne sont pas gérés par Wagtail.

Ce module vit dans « website » et non dans « core » : il connaît les catalogues
de formations, d'e-learning et de bibliothèque, tandis que le socle ne doit
connaître aucun domaine. Recenser les pages publiques est
le travail du portail public, qui agrège les domaines par vocation.
"""

from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from apps.elearning.models import ModuleFormation
from apps.formations.models import Cours, Parcours, Professeur
from apps.library.models import NoticeBibliographique


class PagesPubliquesSitemap(Sitemap):
    """Entrées de catalogue stables, accessibles sans compte."""

    protocol = "https"

    def items(self):
        return (
            "website:politique_donnees",
            "website:politique_cookies",
            "website:mentions_legales",
            "website:articles",
            "admissions:candidature_form",
            "formations:parcours_list",
            "formations:professeur_list",
            "elearning:catalogue",
            "library:catalogue",
        )

    def location(self, item):
        return reverse(item)


class ParcoursSitemap(Sitemap):
    protocol = "https"

    def items(self):
        return Parcours.objects.filter(actif=True).only("slug", "updated_at")

    def lastmod(self, item):
        return item.updated_at


class CoursSitemap(Sitemap):
    protocol = "https"

    def items(self):
        return Cours.objects.filter(actif=True).only("slug", "updated_at")

    def lastmod(self, item):
        return item.updated_at


class ProfesseursSitemap(Sitemap):
    protocol = "https"

    def items(self):
        return Professeur.objects.filter(actif=True).only("slug", "updated_at")

    def lastmod(self, item):
        return item.updated_at


class ModulesPubliesSitemap(Sitemap):
    protocol = "https"

    def items(self):
        return ModuleFormation.objects.filter(statut=ModuleFormation.StatutPublication.PUBLIE).only(
            "slug",
            "updated_at",
        )

    def lastmod(self, item):
        return item.updated_at


class NoticesBibliothequeSitemap(Sitemap):
    protocol = "https"

    def items(self):
        return NoticeBibliographique.objects.only("pk", "updated_at")

    def location(self, item):
        return reverse("library:notice_detail", kwargs={"pk": item.pk})

    def lastmod(self, item):
        return item.updated_at


class ArticlesRechercheSitemap(Sitemap):
    """Les travaux des enseignants et des étudiants.

    Ils sont publics et destinés à être trouvés : c'est ce qui donne de la
    visibilité aux travaux et à l'institut. Les omettre du plan du site
    reviendrait à les publier sans que personne ne les cherche.
    """

    protocol = "https"
    changefreq = "monthly"

    def items(self):
        from apps.website.models_publications import Article

        return Article.objects.filter(statut=Article.Statut.PUBLIE).only("slug", "updated_at")

    def lastmod(self, item):
        return item.updated_at


class TemoignagesPubliesSitemap(Sitemap):
    """Témoignages dont la publication publique a été explicitement consentie."""

    protocol = "https"
    changefreq = "monthly"

    def items(self):
        from apps.website.models_publications import TemoignageEtudiant

        return TemoignageEtudiant.objects.filter(
            statut=TemoignageEtudiant.Statut.PUBLIE,
            consentement_publication=True,
        ).only("pk", "modifie_le")

    def location(self, item):
        return reverse("website:temoignage_public", kwargs={"pk": item.pk})

    def lastmod(self, item):
        return item.modifie_le
