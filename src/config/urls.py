"""
URL configuration — ITEAG Platform.
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.sitemaps.views import sitemap
from django.urls import include, path
from django.views.generic import TemplateView
from wagtail import urls as wagtail_urls
from wagtail.admin import urls as wagtailadmin_urls
from wagtail.contrib.sitemaps.sitemap_generator import Sitemap as WagtailSitemap
from wagtail.documents import urls as wagtaildocs_urls

from apps.core import views as views_core

sitemaps = {
    "wagtail": WagtailSitemap,
}

urlpatterns = [
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
    path("espace-etudiant/", include("apps.academics.urls", namespace="academics")),
    path("espace-enseignant/", include("apps.lms.urls", namespace="lms")),
    path("mes-documents/", include("apps.documents.urls", namespace="documents")),
    path("", include("apps.website.urls", namespace="website")),
    # Wagtail catch-all (must be last)
    path("", include(wagtail_urls)),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

    # Debug toolbar
    try:
        import debug_toolbar

        urlpatterns = [path("__debug__/", include(debug_toolbar.urls))] + urlpatterns
    except ImportError:
        pass

    # Browser reload
    try:
        urlpatterns = [path("__reload__/", include("django_browser_reload.urls"))] + urlpatterns
    except ImportError:
        pass

# ──────────────────────────────────────────────
# Gestionnaires d'erreur — pages à la charte, sans détail technique
# ──────────────────────────────────────────────

handler400 = "apps.core.views.erreur_400"
handler403 = "apps.core.views.erreur_403"
handler404 = "apps.core.views.erreur_404"
handler500 = "apps.core.views.erreur_500"
