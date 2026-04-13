from django.urls import path

from .views import (
    TeacherAnnouncementCreateView,
    TeacherAnnouncementUpdateView,
    TeacherAnnoncesListView,
    TeacherCourseDetailView,
    TeacherCoursesListView,
    TeacherDashboardView,
    TeacherEvaluationsListView,
    TeacherGradeEvaluationView,
    TeacherPublishGradesView,
    TeacherResourceUploadView,
)

app_name = "lms"

urlpatterns = [
    path("", TeacherDashboardView.as_view(), name="dashboard"),
    path("cours/", TeacherCoursesListView.as_view(), name="courses_list"),
    path("cours/<int:pk>/", TeacherCourseDetailView.as_view(), name="course_detail"),
    path("cours/<int:cours_pk>/ressource/", TeacherResourceUploadView.as_view(), name="resource_upload"),
    path("cours/<int:cours_pk>/annonce/", TeacherAnnouncementCreateView.as_view(), name="announcement_create"),
    path("cours/<int:pk>/publier-notes/", TeacherPublishGradesView.as_view(), name="publish_grades"),
    path("evaluations/", TeacherEvaluationsListView.as_view(), name="evaluations_list"),
    path("evaluations/<int:pk>/noter/", TeacherGradeEvaluationView.as_view(), name="grade_evaluation"),
    path("annonces/", TeacherAnnoncesListView.as_view(), name="annonces_list"),
    path("annonces/<int:pk>/modifier/", TeacherAnnouncementUpdateView.as_view(), name="announcement_update"),
]