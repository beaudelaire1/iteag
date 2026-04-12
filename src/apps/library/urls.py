from django.urls import path

from . import views

app_name = "library"

urlpatterns = [
    path("", views.CatalogueView.as_view(), name="catalogue"),
    path("notice/<int:pk>/", views.NoticeDetailView.as_view(), name="notice_detail"),
]
