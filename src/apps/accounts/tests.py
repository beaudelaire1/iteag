import pytest
from apps.accounts.models import User


@pytest.mark.django_db
class TestUserModel:
    def test_create_user(self):
        user = User.objects.create_user(
            username="jean",
            email="jean@iteag.org",
            password="pass123!",
            first_name="Jean",
            last_name="Dupont",
            role="etudiant",
        )
        assert user.pk is not None
        assert user.email == "jean@iteag.org"
        assert user.role == "etudiant"
        assert user.is_etudiant
        assert not user.is_admin

    def test_create_superuser(self):
        admin = User.objects.create_superuser(
            username="superadmin",
            email="superadmin@iteag.org",
            password="admin123!",
        )
        assert admin.is_superuser
        assert admin.is_staff

    def test_default_role(self):
        user = User.objects.create_user(
            username="default",
            email="default@iteag.org",
            password="pass123!",
        )
        assert user.role == "etudiant"

    def test_str_representation(self, user):
        assert str(user) == "Test User"
