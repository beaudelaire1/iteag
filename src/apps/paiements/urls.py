from django.urls import path

from . import views

app_name = "paiements"

urlpatterns = [
    path("stripe/webhook/", views.WebhookStripeView.as_view(), name="webhook_stripe"),
    path("module/<slug:slug>/acheter/", views.AchatModuleView.as_view(), name="acheter_module"),
    path("<uuid:pk>/succes/", views.SuccesView.as_view(), name="succes"),
    path("<uuid:pk>/annulation/", views.AnnulationView.as_view(), name="annulation"),
    path("<uuid:pk>/recu/", views.SuccesView.as_view(), name="recu"),
]
