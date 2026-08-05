"""Routes de rédaction, servies sous « /espace-admin/documents/ ».

À part de « urls.py », qui vit sous « /mes-documents/ » et n'appartient qu'à
l'étudiant. Deux publics, deux préfixes : la même application peut servir les
deux sans que l'un hérite des adresses de l'autre.
"""

from django.urls import path

from . import vues_redaction

app_name = "redaction"

urlpatterns = [
    path("", vues_redaction.DocumentsRedigesView.as_view(), name="documents"),
    path("nouveau/", vues_redaction.DocumentRedigeEditionView.as_view(), name="document_creation"),
    path("<int:pk>/", vues_redaction.DocumentRedigeEditionView.as_view(), name="document_edition"),
    path("<int:pk>/decision/", vues_redaction.DocumentRedigeDecisionView.as_view(), name="document_decision"),
    path("<int:pk>/etat-pdf/", vues_redaction.DocumentRedigeEtatView.as_view(), name="document_etat_pdf"),
    path("<int:pk>/pdf/", vues_redaction.DocumentRedigePdfView.as_view(), name="document_pdf"),
]
