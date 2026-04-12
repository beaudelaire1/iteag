from django.urls import path

from . import views

app_name = "admissions"

urlpatterns = [
    path("candidature/", views.candidature_form, name="candidature_form"),
    path("candidature/parcours-apercu/", views.parcours_preview, name="parcours_preview"),
    path("candidature/confirmation/<str:token>/", views.candidature_confirmation, name="candidature_confirmation"),
    path("candidature/suivi/<str:token>/", views.candidature_suivi, name="candidature_suivi"),
]
