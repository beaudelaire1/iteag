"""Sitemaps des contenus publics qui ne sont pas gérés par Wagtail.

Ce module vit dans « website » et non dans « core » : il connaît le catalogue
de quatre domaines — formations, e-learning, bibliothèque, boutique — et le
socle, lui, ne doit connaître personne. Placé dans « core », il y faisait
entrer commerce et library, et refermait le cycle
« accounts → core → commerce → accounts ». Recenser les pages publiques est
le travail du portail public, qui agrège les domaines par vocation.
"""

from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from apps.commerce.models import ProduitLivre
from apps.elearning.models import ModuleFormation
from apps.formations.models import Cours, Parcours, Professeur
from apps.library.models import NoticeBibliographique


class PagesPubliquesSitemap(Sitemap):
    """Entrées de catalogue stables, accessibles sans compte."""

    protocol = "https"

    def items(self):
        return (
            "formations:parcours_list",
            "formations:professeur_list",
            "elearning:catalogue",
            "library:catalogue",
            "commerce:catalogue",
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


class LivresBoutiqueSitemap(Sitemap):
    protocol = "https"

    def items(self):
        return ProduitLivre.objects.filter(actif=True).only("slug", "updated_at")

    def lastmod(self, item):
        return item.updated_at


class ArticlesRechercheSitemap(Sitemap):
    """Les travaux des enseignants-chercheurs.

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
