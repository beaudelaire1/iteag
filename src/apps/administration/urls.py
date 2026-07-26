from django.urls import path

from . import views, views_academics, views_elearning

app_name = "administration"

urlpatterns = [
    path("", views.AdminDashboardView.as_view(), name="dashboard"),
    # Candidatures
    path("candidatures/", views.AdminCandidatureListView.as_view(), name="candidatures"),
    path("candidatures/<int:pk>/", views.AdminCandidatureDetailView.as_view(), name="candidature_detail"),
    # Étudiants
    path("etudiants/", views.AdminEtudiantListView.as_view(), name="etudiants"),
    path("etudiants/ajouter/", views.AdminEtudiantCreateView.as_view(), name="etudiant_create"),
    path("etudiants/<int:pk>/modifier/", views.AdminEtudiantUpdateView.as_view(), name="etudiant_update"),
    path("etudiants/<int:pk>/supprimer/", views.AdminEtudiantDeleteView.as_view(), name="etudiant_delete"),
    # Professeurs
    path("professeurs/", views.AdminProfesseurListView.as_view(), name="professeurs"),
    path("professeurs/ajouter/", views.AdminProfesseurCreateView.as_view(), name="professeur_create"),
    path("professeurs/<int:pk>/modifier/", views.AdminProfesseurUpdateView.as_view(), name="professeur_update"),
    path("professeurs/<int:pk>/supprimer/", views.AdminProfesseurDeleteView.as_view(), name="professeur_delete"),
    # Formations
    path("formations/", views.AdminFormationsView.as_view(), name="formations"),
    path("formations/cours/", views_academics.CourseListView.as_view(), name="courses"),
    path("formations/cours/ajouter/", views_academics.CourseCreateView.as_view(), name="course_create"),
    path(
        "formations/cours/<int:pk>/modifier/",
        views_academics.CourseUpdateView.as_view(),
        name="course_update",
    ),
    path(
        "formations/cours/<int:pk>/supprimer/",
        views_academics.CourseDeleteView.as_view(),
        name="course_delete",
    ),
    # Sessions
    path("sessions/", views.AdminSessionListView.as_view(), name="sessions"),
    path("sessions/ajouter/", views.AdminSessionCreateView.as_view(), name="session_create"),
    path("sessions/<int:pk>/modifier/", views.AdminSessionUpdateView.as_view(), name="session_update"),
    path("sessions/<int:pk>/supprimer/", views.AdminSessionDeleteView.as_view(), name="session_delete"),
    # Programmation des cours
    path("offre-cours/", views_academics.CourseOfferingListView.as_view(), name="course_offerings"),
    path(
        "offre-cours/ajouter/",
        views_academics.CourseOfferingCreateView.as_view(),
        name="course_offering_create",
    ),
    path(
        "offre-cours/<int:pk>/modifier/",
        views_academics.CourseOfferingUpdateView.as_view(),
        name="course_offering_update",
    ),
    path(
        "offre-cours/<int:pk>/supprimer/",
        views_academics.CourseOfferingDeleteView.as_view(),
        name="course_offering_delete",
    ),
    # Demandes d'inscription aux cours
    path("inscriptions-cours/", views_academics.EnrollmentRequestListView.as_view(), name="enrollment_requests"),
    path(
        "inscriptions-cours/<int:pk>/",
        views_academics.EnrollmentRequestDetailView.as_view(),
        name="enrollment_request_detail",
    ),
    path(
        "inscriptions-cours/<int:pk>/action/",
        views_academics.EnrollmentRequestActionView.as_view(),
        name="enrollment_request_action",
    ),
    path(
        "inscriptions-cours/<int:pk>/justificatif/",
        views_academics.EnrollmentProofDownloadView.as_view(),
        name="enrollment_proof_download",
    ),
    # Paiements
    path("paiements/", views_academics.PaymentListView.as_view(), name="payments"),
    path("paiements/ajouter/", views_academics.PaymentCreateView.as_view(), name="payment_create"),
    path("paiements/<int:pk>/modifier/", views_academics.PaymentUpdateView.as_view(), name="payment_update"),
    path("paiements/<int:pk>/supprimer/", views_academics.PaymentDeleteView.as_view(), name="payment_delete"),
    # Utilisateurs
    path("utilisateurs/", views.AdminUserListView.as_view(), name="utilisateurs"),
    path("utilisateurs/ajouter/", views.AdminUserCreateView.as_view(), name="user_create"),
    path("utilisateurs/<int:pk>/modifier/", views.AdminUserUpdateView.as_view(), name="user_update"),
    path("utilisateurs/<int:pk>/supprimer/", views.AdminUserDeleteView.as_view(), name="user_delete"),
    # Exports CSV
    path("export/candidatures/", views.ExportCandidaturesCsvView.as_view(), name="export_candidatures"),
    path("export/etudiants/", views.ExportEtudiantsCsvView.as_view(), name="export_etudiants"),
    path("export/paiements/", views.ExportPaiementsCsvView.as_view(), name="export_paiements"),
    # Actions groupées
    path("candidatures/bulk-status/", views.BulkCandidatureStatusView.as_view(), name="candidatures_bulk_status"),
    # ── Formation vidéo : pilotage des accès ──
    path("formation-video/acces/", views_elearning.AccesListView.as_view(), name="acces"),
    path("formation-video/acces/action/", views_elearning.AccesActionView.as_view(), name="acces_action"),
    path("formation-video/acces/octroi-masse/", views_elearning.OctroiEnMasseView.as_view(), name="acces_octroi_masse"),
    path("formation-video/acces/export/", views_elearning.ExportAccesView.as_view(), name="acces_export"),
    path("formation-video/statistiques/", views_elearning.StatistiquesVideoView.as_view(), name="video_statistiques"),
    path("formation-video/journal/", views_elearning.JournalAccesView.as_view(), name="video_journal"),
]
