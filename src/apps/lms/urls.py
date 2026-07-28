from django.urls import path

from .views import (
    TeacherAnnoncesListView,
    TeacherAnnouncementCreateView,
    TeacherAnnouncementDeleteView,
    TeacherAnnouncementUpdateView,
    TeacherCourseDetailView,
    TeacherCoursesListView,
    TeacherDashboardView,
    TeacherEvaluationsListView,
    TeacherGradeEvaluationView,
    TeacherPrepareEvaluationsView,
    TeacherPublishGradesView,
    TeacherResourceDeleteView,
    TeacherResourceUpdateView,
    TeacherResourceUploadView,
)
from .views_devoirs import (
    TeacherDelaiView,
    TeacherDevoirActionView,
    TeacherDevoirCreateView,
    TeacherDevoirDetailView,
    TeacherDevoirsListView,
    TeacherDevoirUpdateView,
    TeacherEtudiantsListView,
    TeacherReviseGradeView,
)

app_name = "lms"

urlpatterns = [
    path("", TeacherDashboardView.as_view(), name="dashboard"),
    # ── Devoirs ──
    path("devoirs/", TeacherDevoirsListView.as_view(), name="devoirs_list"),
    path("cours/<int:cours_pk>/devoir/", TeacherDevoirCreateView.as_view(), name="devoir_create"),
    path("devoirs/<int:pk>/", TeacherDevoirDetailView.as_view(), name="devoir_detail"),
    path("devoirs/<int:pk>/modifier/", TeacherDevoirUpdateView.as_view(), name="devoir_update"),
    path("devoirs/<int:pk>/action/", TeacherDevoirActionView.as_view(), name="devoir_action"),
    path("copies/<int:pk>/delai/", TeacherDelaiView.as_view(), name="accorder_delai"),
    # ── Recours ──
    path("evaluations/<int:pk>/reviser/", TeacherReviseGradeView.as_view(), name="revise_grade"),
    # ── Mes étudiants ──
    path("etudiants/", TeacherEtudiantsListView.as_view(), name="etudiants_list"),
    path("cours/", TeacherCoursesListView.as_view(), name="courses_list"),
    path("cours/<int:pk>/", TeacherCourseDetailView.as_view(), name="course_detail"),
    path("cours/<int:cours_pk>/ressource/", TeacherResourceUploadView.as_view(), name="resource_upload"),
    path("ressources/<int:pk>/modifier/", TeacherResourceUpdateView.as_view(), name="resource_update"),
    path("ressources/<int:pk>/supprimer/", TeacherResourceDeleteView.as_view(), name="resource_delete"),
    path("cours/<int:cours_pk>/annonce/", TeacherAnnouncementCreateView.as_view(), name="announcement_create"),
    path("cours/<int:pk>/publier-notes/", TeacherPublishGradesView.as_view(), name="publish_grades"),
    path("cours/<int:pk>/preparer-evaluations/", TeacherPrepareEvaluationsView.as_view(), name="prepare_evaluations"),
    path("evaluations/", TeacherEvaluationsListView.as_view(), name="evaluations_list"),
    path("evaluations/<int:pk>/noter/", TeacherGradeEvaluationView.as_view(), name="grade_evaluation"),
    path("annonces/", TeacherAnnoncesListView.as_view(), name="annonces_list"),
    path("annonces/<int:pk>/modifier/", TeacherAnnouncementUpdateView.as_view(), name="announcement_update"),
    path("annonces/<int:pk>/supprimer/", TeacherAnnouncementDeleteView.as_view(), name="announcement_delete"),
]
