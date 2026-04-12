from django.urls import path

from .views import IteagLoginView, IteagLogoutView

app_name = "accounts"

urlpatterns = [
    path("connexion/", IteagLoginView.as_view(), name="login"),
    path("deconnexion/", IteagLogoutView.as_view(), name="logout"),
]