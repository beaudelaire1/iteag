import pytest
from django.test import RequestFactory

from apps.accounts.models import User


@pytest.fixture(autouse=True)
def _cache_vierge():
    """
    Vide le cache avant chaque test.

    La base est rendue à son état initial entre les tests, ce qui réattribue
    les mêmes identifiants ; le cache, lui, survit à toute la session. Une clé
    comme « elearning:flux:{pk} » — le verrou de lecture simultanée — était
    donc reprise d'un test à l'autre et refusait une lecture parfaitement
    légitime. Le symptôme est un 429 apparaissant selon l'ordre d'exécution :
    le genre d'échec qu'on met une matinée à comprendre.
    """
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()


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
