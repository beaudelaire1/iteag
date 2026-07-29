from django.urls import path

from . import views, views_enseignant

app_name = "elearning"

urlpatterns = [
    # Catalogue et fiches
    path("", views.CataloguePublicView.as_view(), name="catalogue"),
    path("mes-formations/", views.MesFormationsView.as_view(), name="mes_formations"),
    path("attestation/verifier/<str:code>/", views.VerifierAttestationView.as_view(), name="verifier_attestation"),
    path("attestation/<uuid:pk>/", views.AttestationTelechargementView.as_view(), name="attestation_telecharger"),
    # Service de fichier signé (stockage local uniquement)
    path("fichier/<str:jeton>/", views.FichierVideoView.as_view(), name="fichier_video"),
    # ── Portail enseignant : production du contenu ──
    path("espace-enseignant/", views_enseignant.TableauDeBordVideoView.as_view(), name="enseignant_tableau"),
    path("espace-enseignant/modules/", views_enseignant.MesModulesView.as_view(), name="enseignant_modules"),
    path(
        "espace-enseignant/modules/nouveau/",
        views_enseignant.ModuleCreateView.as_view(),
        name="enseignant_module_creer",
    ),
    path("espace-enseignant/videos/", views_enseignant.VideoUploadView.as_view(), name="enseignant_videos"),
    path(
        "espace-enseignant/videos/<uuid:video_pk>/sous-titres/",
        views_enseignant.SousTitreCreateView.as_view(),
        name="enseignant_soustitre",
    ),
    path(
        "espace-enseignant/videos/<uuid:pk>/supprimer/",
        views_enseignant.VideoDeleteView.as_view(),
        name="enseignant_video_supprimer",
    ),
    path(
        "espace-enseignant/chapitres/<int:chapitre_pk>/lecon/",
        views_enseignant.LeconCreateView.as_view(),
        name="enseignant_lecon_creer",
    ),
    path(
        "espace-enseignant/chapitres/<int:chapitre_pk>/ordonner/",
        views_enseignant.ReordonnerLeconsView.as_view(),
        name="enseignant_lecons_ordonner",
    ),
    path(
        "espace-enseignant/chapitres/<int:pk>/supprimer/",
        views_enseignant.ChapitreDeleteView.as_view(),
        name="enseignant_chapitre_supprimer",
    ),
    path(
        "espace-enseignant/lecons/<uuid:pk>/modifier/",
        views_enseignant.LeconUpdateView.as_view(),
        name="enseignant_lecon_modifier",
    ),
    path(
        "espace-enseignant/lecons/<uuid:pk>/supprimer/",
        views_enseignant.LeconDeleteView.as_view(),
        name="enseignant_lecon_supprimer",
    ),
    path(
        "espace-enseignant/lecons/<uuid:lecon_pk>/ressources/",
        views_enseignant.RessourceCreateView.as_view(),
        name="enseignant_ressource_creer",
    ),
    path(
        "espace-enseignant/ressources/<int:pk>/supprimer/",
        views_enseignant.RessourceDeleteView.as_view(),
        name="enseignant_ressource_supprimer",
    ),
    path(
        "espace-enseignant/<slug:slug>/chapitre/",
        views_enseignant.ChapitreCreateView.as_view(),
        name="enseignant_chapitre_creer",
    ),
    path("espace-enseignant/<slug:slug>/", views_enseignant.ModuleStructureView.as_view(), name="enseignant_structure"),
    path(
        "espace-enseignant/<slug:slug>/modifier/",
        views_enseignant.ModuleUpdateView.as_view(),
        name="enseignant_module_modifier",
    ),
    path(
        "espace-enseignant/<slug:slug>/publier/",
        views_enseignant.ModulePublierView.as_view(),
        name="enseignant_publier",
    ),
    path(
        "espace-enseignant/<slug:slug>/depublier/",
        views_enseignant.ModuleDepublierView.as_view(),
        name="enseignant_depublier",
    ),
    path(
        "espace-enseignant/<slug:slug>/audience/", views_enseignant.AudienceView.as_view(), name="enseignant_audience"
    ),
    # Module et leçons
    path("<slug:slug>/", views.ModuleDetailView.as_view(), name="module_detail"),
    # Doit précéder « lecon_detail », qui capterait sinon « demander-acces »
    # comme s'il s'agissait du slug d'une leçon.
    path(
        "<slug:slug>/demander-acces/",
        views.DemandeAccesModuleView.as_view(),
        name="module_demander_acces",
    ),
    path("<slug:slug>/<slug:lecon_slug>/", views.LeconDetailView.as_view(), name="lecon_detail"),
    path(
        "<slug:slug>/<slug:lecon_slug>/ressources/<int:pk>/",
        views.RessourceTelechargementView.as_view(),
        name="ressource_telecharger",
    ),
    path("<slug:slug>/<slug:lecon_slug>/lecture/", views.playback_url, name="lecon_playback"),
    path("<slug:slug>/<slug:lecon_slug>/progression/", views.ProgressionView.as_view(), name="lecon_progression"),
]
