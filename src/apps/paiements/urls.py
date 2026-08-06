from django.urls import path

from . import views

app_name = "paiements"

urlpatterns = [
    path("stripe/webhook/", views.WebhookStripeView.as_view(), name="webhook_stripe"),
    path("module/<slug:slug>/acheter/", views.AchatModuleView.as_view(), name="acheter_module"),
    path(
        "inscription/<int:pk>/payer/",
        views.PaiementInscriptionView.as_view(),
        name="payer_inscription",
    ),
    path(
        "commande/<uuid:jeton>/payer/",
        views.PaiementCommandeView.as_view(),
        name="payer_commande",
    ),
    path("<uuid:pk>/payer/", views.CheckoutView.as_view(), name="checkout"),
    path("<uuid:pk>/session/", views.SessionCheckoutView.as_view(), name="session_checkout"),
    path("<uuid:pk>/succes/", views.SuccesView.as_view(), name="succes"),
    path("<uuid:pk>/annulation/", views.AnnulationView.as_view(), name="annulation"),
    path("<uuid:pk>/recu/", views.SuccesView.as_view(), name="recu"),
]
