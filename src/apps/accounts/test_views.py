import pytest
from django.test import Client
from django.urls import reverse

from apps.accounts.models import User


# ──────────────────────────────────────────────
# Auth views
# ──────────────────────────────────────────────


@pytest.mark.django_db
class TestLoginView:
    def test_login_page_get(self, client: Client):
        url = reverse("accounts:login")
        response = client.get(url)
        assert response.status_code == 200

    def test_login_valid(self, client: Client, user):
        url = reverse("accounts:login")
        response = client.post(url, {"username": "testuser", "password": "testpass123!"})
        assert response.status_code == 302  # redirect on success

    def test_login_invalid(self, client: Client, user):
        url = reverse("accounts:login")
        response = client.post(url, {"username": "testuser", "password": "wrong"})
        assert response.status_code == 200  # re-renders form


@pytest.mark.django_db
class TestLogoutView:
    def test_logout(self, client: Client, user):
        client.force_login(user)
        url = reverse("accounts:logout")
        response = client.post(url)
        assert response.status_code == 302


@pytest.mark.django_db
class TestPasswordResetViews:
    def test_reset_form_get(self, client: Client):
        url = reverse("accounts:password_reset")
        response = client.get(url)
        assert response.status_code == 200

    def test_reset_done_get(self, client: Client):
        url = reverse("accounts:password_reset_done")
        response = client.get(url)
        assert response.status_code == 200

    def test_reset_complete_get(self, client: Client):
        url = reverse("accounts:password_reset_complete")
        response = client.get(url)
        assert response.status_code == 200
