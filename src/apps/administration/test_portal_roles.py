import pytest
from django.urls import reverse

from apps.accounts.models import User

from .forms import AdminUserCreateForm


@pytest.fixture
def secretary(db):
    return User.objects.create_user(
        username="secretariat",
        password="valid-password-123",
        role=User.Role.SECRETARIAT,
    )


@pytest.mark.django_db
class TestPortalRoleSeparation:
    def test_secretary_has_operational_portal(self, client, secretary):
        client.force_login(secretary)
        assert client.get(reverse("secretariat:dashboard")).status_code == 200
        assert client.get(reverse("administration:candidatures")).status_code == 200
        assert client.get(reverse("administration:etudiants")).status_code == 200
        assert client.get(reverse("administration:sessions")).status_code == 200

    @pytest.mark.parametrize(
        "route",
        [
            "administration:dashboard",
            "administration:utilisateurs",
            "administration:professeurs",
            "administration:formations",
            "administration:session_create",
        ],
    )
    def test_secretary_cannot_access_governance(self, client, secretary, route):
        client.force_login(secretary)
        assert client.get(reverse(route)).status_code == 403


@pytest.mark.django_db
def test_admin_user_form_applies_django_password_validation():
    form = AdminUserCreateForm(
        data={
            "username": "weak-password-user",
            "first_name": "Weak",
            "last_name": "Password",
            "email": "weak@example.com",
            "phone": "",
            "role": User.Role.ETUDIANT,
            "is_active": True,
            "password1": "123",
        }
    )
    assert not form.is_valid()
    assert "password1" in form.errors
