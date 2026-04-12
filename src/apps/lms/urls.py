from django.urls import path

from .views import TeacherCourseDetailView, TeacherDashboardView

app_name = "lms"

urlpatterns = [
    path("", TeacherDashboardView.as_view(), name="dashboard"),
    path("cours/<int:pk>/", TeacherCourseDetailView.as_view(), name="course_detail"),
]