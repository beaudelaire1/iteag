from django.urls import path

from .views import StudentCoursesView, StudentDashboardView, StudentGradesView, StudentProgressView

app_name = "academics"

urlpatterns = [
    path("", StudentDashboardView.as_view(), name="dashboard"),
    path("parcours/", StudentProgressView.as_view(), name="progress"),
    path("cours/", StudentCoursesView.as_view(), name="courses"),
    path("notes/", StudentGradesView.as_view(), name="grades"),
]