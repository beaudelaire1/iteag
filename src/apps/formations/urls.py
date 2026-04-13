from django.urls import path

from . import views

app_name = "formations"

urlpatterns = [
    path("", views.ParcoursListView.as_view(), name="parcours_list"),
    path("parcours/<slug:slug>/", views.ParcoursDetailView.as_view(), name="parcours_detail"),
    path("cours/<slug:slug>/", views.CoursDetailView.as_view(), name="cours_detail"),
    path("professeurs/", views.ProfesseurListView.as_view(), name="professeur_list"),
    path("professeurs/<slug:slug>/", views.ProfesseurDetailView.as_view(), name="professeur_detail"),
]
