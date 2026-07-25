from django.urls import path

from . import views

app_name = "secretariat"

urlpatterns = [
    path("", views.SecretariatDashboardView.as_view(), name="dashboard"),
]
