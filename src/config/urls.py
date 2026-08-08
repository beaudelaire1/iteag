"""
URL configuration — ITEAG Platform.
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.sitemaps.views import sitemap
from django.urls import include, path, re_path
from django.views.generic import RedirectView, TemplateView
from wagtail import urls as wagtail_urls
from wagtail.admin import urls as wagtailadmin_urls
from wagtail.contrib.sitemaps.sitemap_generator import Sitemap as WagtailSitemap
from wagtail.documents import urls as wagtaildocs_urls

from apps.core import views as views_core
from apps.website.sitemaps import (
    ArticlesRechercheSitemap,
    CoursSitemap,
    LivresBoutiqueSitemap,
    ModulesPubliesSitemap,
    NoticesBibliothequeSitemap,
    PagesPubliquesSitemap,
    ParcoursSitemap,
    ProfesseursSitemap,
)

sitemaps = {
    "wagtail": WagtailSitemap,
    "pages-publiques": PagesPubliquesSitemap,
    "articles": ArticlesRechercheSitemap,
    "parcours": ParcoursSitemap,
    "cours": CoursSitemap,
    "professeurs": ProfesseursSitemap,
    "modules": ModulesPubliesSitemap,
    "bibliotheque": NoticesBibliothequeSitemap,
    "boutique": LivresBoutiqueSitemap,
}

# Migration de l'ancien site public vers la nouvelle arborescence. Ces routes
# doivent rester avant Wagtail : une URL historiquement indexée doit répondre
# par une redirection permanente et non être capturée comme une page inconnue.
# query_string=True conserve les paramètres de campagne et autres marqueurs
# éventuellement présents dans des liens externes existants.
URLS_PUBLIQUES_HISTORIQUES = {
    "presentation": "/presentation/",
    "education": "/formations/",
    "diploma": "/formations/parcours/diplomant-iteag/",
    "educationinministry": "/formations/parcours/iteag-pro/",
    "enroll": "/candidature/",
    # Deux slugs ont existé dans le footer de la refonte avant la bascule. Les
    # conserver en 301 évite qu'un lien partagé pendant la recette devienne mort.
    "formations/parcours/parcours-diplomant-iteag/": "/formations/parcours/diplomant-iteag/",
    "formations/parcours/parcours-bachelor-flte/": "/formations/parcours/bachelor-flte/",
}

urlpatterns = [
    *[
        path(
            ancienne_url,
            RedirectView.as_view(url=nouvelle_url, permanent=True, query_string=True),
            name=f"ancienne_url_publique_{index}",
        )
        for index, (ancienne_url, nouvelle_url) in enumerate(URLS_PUBLIQUES_HISTORIQUES.items())
    ],
    # Django admin
    path("django-admin/", admin.site.urls),
    # SEO
    path("sitemap.xml", sitemap, {"sitemaps": sitemaps}, name="django.contrib.sitemaps.views.sitemap"),
    path("robots.txt", TemplateView.as_view(template_name="robots.txt", content_type="text/plain")),
    # Sonde de santé (supervision et HEALTHCHECK du conteneur)
    path("healthz", views_core.HealthzView.as_view(), name="healthz"),
    # Wagtail admin
    path("admin/", include(wagtailadmin_urls)),
    path("documents/", include(wagtaildocs_urls)),
    # Local apps
    path("", include("apps.core.urls", namespace="core")),
    path("", include("apps.accounts.urls", namespace="accounts")),
    path("espace-admin/", include("apps.administration.urls", namespace="administration")),
    path(
        "espace-secretariat/",
        include("apps.administration.secretariat_urls", namespace="secretariat"),
    ),
    path("formations/", include("apps.formations.urls", namespace="formations")),
    path("admissions/", include("apps.admissions.urls", namespace="admissions")),
    path("bibliotheque/", include("apps.library.urls", namespace="library")),
    path("boutique/", include("apps.commerce.urls", namespace="commerce")),
    path("paiements/", include("apps.paiements.urls", namespace="paiements")),
    path("espace-etudiant/", include("apps.portail_etudiant.urls", namespace="etudiant")),
    path("espace-enseignant/", include("apps.portail_enseignant.urls", namespace="enseignant")),
    path("espace-enseignant/", include("apps.lms.urls", namespace="lms")),
    path("mes-documents/", include("apps.documents.urls", namespace="documents")),
    # Même application, second public : l'étudiant génère ses pièces sous
    # « mes-documents/ », le personnel rédige les courriers de l'institut ici.
    path(
        "espace-admin/documents/",
        include("apps.documents.redaction_urls", namespace="redaction"),
    ),
    path("e-learning/", include("apps.elearning.urls", namespace="elearning")),
    re_path(
        r"^formations-video/(?P<chemin>.*)$",
        RedirectView.as_view(
            url="/e-learning/%(chemin)s",
            permanent=True,
            query_string=True,
        ),
        name="ancienne_url_elearning",
    ),
    # « espace-enseignant/ » avait été amputé de ses cinq premières lettres en
    # même temps qu'on ajoutait les questionnaires (12a8e78), sans que personne
    # ne l'ait voulu ni remarqué : le préfixe est devenu « gnant/ ». Les liens
    # posés entre-temps méritent d'aboutir plutôt que de tomber en 404, d'où
    # cette redirection — la même mécanique que pour l'ancienne URL e-learning.
    re_path(
        r"^gnant/(?P<chemin>.*)$",
        RedirectView.as_view(
            url="/espace-enseignant/%(chemin)s",
            permanent=True,
            query_string=True,
        ),
        name="ancienne_url_enseignant",
    ),
    path("", include("apps.website.urls", namespace="website")),
    # Wagtail catch-all (must be last)
    path("", include(wagtail_urls)),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

    # Debug toolbar
    if "debug_toolbar" in settings.INSTALLED_APPS:
        import debug_toolbar

        urlpatterns = [path("__debug__/", include(debug_toolbar.urls))] + urlpatterns

    # Browser reload
    if "django_browser_reload" in settings.INSTALLED_APPS:
        import django_browser_reload

        urlpatterns = [path("__reload__/", include(django_browser_reload.urls))] + urlpatterns

# ──────────────────────────────────────────────
# Gestionnaires d'erreur — pages à la charte, sans détail technique
# ──────────────────────────────────────────────

handler400 = "apps.core.views.erreur_400"
handler403 = "apps.core.views.erreur_403"
handler404 = "apps.core.views.erreur_404"
handler500 = "apps.core.views.erreur_500"
