import pytest
from django.contrib.auth.hashers import PBKDF2PasswordHasher, identify_hasher
from django.core import mail
from django.test import Client, override_settings
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

    @override_settings(
        PASSWORD_HASHERS=[
            "django.contrib.auth.hashers.ScryptPasswordHasher",
            "django.contrib.auth.hashers.PBKDF2PasswordHasher",
        ]
    )
    def test_un_ancien_mot_de_passe_pbkdf2_migre_vers_scrypt(self, db):
        ancien = PBKDF2PasswordHasher()
        # Une seule itération suffit ici : le test protège la migration de
        # format, pas le coût cryptographique exercé en production.
        ancien.iterations = 1
        utilisateur = User.objects.create(
            username="migration_hash",
            password=ancien.encode("mot-de-passe-long-12", ancien.salt()),
        )

        assert utilisateur.check_password("mot-de-passe-long-12")
        utilisateur.refresh_from_db()
        assert identify_hasher(utilisateur.password).algorithm == "scrypt"


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

    def test_une_demande_valide_envoie_le_lien(self, client: Client, user):
        response = client.post(reverse("accounts:password_reset"), {"email": user.email})

        assert response.status_code == 302
        assert len(mail.outbox) == 1
        assert reverse("accounts:password_reset_done") == response.url
        assert "/mot-de-passe/confirmer/" in mail.outbox[0].body
        assert mail.outbox[0].alternatives
