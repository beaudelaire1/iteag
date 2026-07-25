from django.urls import path

from . import views

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
    # Sessions
    path("sessions/", views.AdminSessionListView.as_view(), name="sessions"),
    path("sessions/ajouter/", views.AdminSessionCreateView.as_view(), name="session_create"),
    path("sessions/<int:pk>/modifier/", views.AdminSessionUpdateView.as_view(), name="session_update"),
    path("sessions/<int:pk>/supprimer/", views.AdminSessionDeleteView.as_view(), name="session_delete"),
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
]
