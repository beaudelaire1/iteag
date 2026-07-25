from django.urls import path

from . import views

app_name = "elearning"

urlpatterns = [
    # Catalogue et fiches
    path("", views.CataloguePublicView.as_view(), name="catalogue"),
    path("mes-formations/", views.MesFormationsView.as_view(), name="mes_formations"),
    path("attestation/verifier/<str:code>/", views.VerifierAttestationView.as_view(), name="verifier_attestation"),
    path("attestation/<uuid:pk>/", views.AttestationTelechargementView.as_view(), name="attestation_telecharger"),
    # Service de fichier signé (stockage local uniquement)
    path("fichier/<str:jeton>/", views.FichierVideoView.as_view(), name="fichier_video"),
    # Module et leçons
    path("<slug:slug>/", views.ModuleDetailView.as_view(), name="module_detail"),
    path("<slug:slug>/<slug:lecon_slug>/", views.LeconDetailView.as_view(), name="lecon_detail"),
    path("<slug:slug>/<slug:lecon_slug>/lecture/", views.playback_url, name="lecon_playback"),
    path("<slug:slug>/<slug:lecon_slug>/progression/", views.ProgressionView.as_view(), name="lecon_progression"),
]
