from django.urls import path

from . import views

app_name = "website"

urlpatterns = [
    path("contact/merci/", views.contact_success, name="contact_success"),
]
