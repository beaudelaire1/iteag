from django.urls import path

from .vues import AccueilEnseignantView
from .vues_propositions import PropositionListView, PropositionReponseView

app_name = "enseignant"

urlpatterns = [
    path("", AccueilEnseignantView.as_view(), name="accueil"),
    path("propositions/", PropositionListView.as_view(), name="propositions"),
    path(
        "propositions/<int:pk>/reponse/",
        PropositionReponseView.as_view(),
        name="proposition_reponse",
    ),
]
