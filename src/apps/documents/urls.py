from django.urls import path

from .views import (
    DownloadStudentDocumentView,
    GenerateStudentDocumentView,
    StudentDocumentListView,
    StudentDocumentStatusView,
)

app_name = "documents"

urlpatterns = [
    path("", StudentDocumentListView.as_view(), name="list"),
    path("generer/<str:document_type>/", GenerateStudentDocumentView.as_view(), name="generate"),
    path("etat/<int:pk>/", StudentDocumentStatusView.as_view(), name="status"),
    path("telecharger/<int:pk>/", DownloadStudentDocumentView.as_view(), name="download"),
]
