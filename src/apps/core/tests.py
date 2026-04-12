import pytest
from apps.core.models import TimeStampedModel, UUIDModel


@pytest.mark.django_db
class TestCoreModels:
    def test_timestamped_is_abstract(self):
        assert TimeStampedModel._meta.abstract is True

    def test_uuid_is_abstract(self):
        assert UUIDModel._meta.abstract is True
