from django.urls import path

from apps.lms.views_qcm import StudentQuestionnaireView

from .vues import (
    StudentCoursesView,
    StudentDashboardView,
    StudentEvaluationSubmitView,
    StudentGradesView,
    StudentProgressView,
)
from .vues_inscription import (
    CourseCatalogueView,
    CourseOfferingDetailView,
    EnrollmentRequestCancelView,
    EnrollmentRequestCreateView,
    MyEnrollmentRequestsView,
    StudentPaymentsView,
)
from .vues_temoignage import TemoignageEtudiantView

app_name = "etudiant"

urlpatterns = [
    path("", StudentDashboardView.as_view(), name="dashboard"),
    path("parcours/", StudentProgressView.as_view(), name="progress"),
    path("cours/", StudentCoursesView.as_view(), name="courses"),
    path("catalogue/", CourseCatalogueView.as_view(), name="course_catalogue"),
    path("catalogue/<int:pk>/", CourseOfferingDetailView.as_view(), name="course_offering_detail"),
    path(
        "catalogue/<int:pk>/demander/",
        EnrollmentRequestCreateView.as_view(),
        name="enrollment_request_create",
    ),
    path("inscriptions/", MyEnrollmentRequestsView.as_view(), name="enrollment_requests"),
    path(
        "inscriptions/<int:pk>/annuler/",
        EnrollmentRequestCancelView.as_view(),
        name="enrollment_request_cancel",
    ),
    path("paiements/", StudentPaymentsView.as_view(), name="payments"),
    path("notes/", StudentGradesView.as_view(), name="grades"),
    path("temoignage/", TemoignageEtudiantView.as_view(), name="temoignage"),
    path("evaluations/<int:pk>/remettre/", StudentEvaluationSubmitView.as_view(), name="submit_evaluation"),
    path("evaluations/<int:pk>/questionnaire/", StudentQuestionnaireView.as_view(), name="questionnaire"),
]
