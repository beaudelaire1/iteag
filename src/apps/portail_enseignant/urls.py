from django.urls import path

from .vues import AccueilEnseignantView

app_name = "enseignant"

urlpatterns = [
    path("", AccueilEnseignantView.as_view(), name="accueil"),
]
