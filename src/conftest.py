import pytest
from django.test import RequestFactory

from apps.accounts.models import User


@pytest.fixture
def request_factory():
    return RequestFactory()


@pytest.fixture
def user(db):
    return User.objects.create_user(
        username="testuser",
        email="test@iteag.org",
        password="testpass123!",
        first_name="Test",
        last_name="User",
    )


@pytest.fixture
def admin_user(db):
    return User.objects.create_superuser(
        username="admin",
        email="admin@iteag.org",
        password="adminpass123!",
    )
