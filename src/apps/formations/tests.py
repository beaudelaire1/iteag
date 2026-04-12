import pytest
from django.test import Client
from django.urls import reverse


@pytest.mark.django_db
class TestFormationsViews:
    def test_parcours_list_view(self, client: Client):
        url = reverse("formations:parcours_list")
        response = client.get(url)
        assert response.status_code == 200

    def test_professeur_list_view(self, client: Client):
        url = reverse("formations:professeur_list")
        response = client.get(url)
        assert response.status_code == 200


@pytest.mark.django_db
class TestFormationsModels:
    def test_discipline_creation(self):
        from apps.formations.models import Discipline

        d = Discipline.objects.create(
            nom="Théologie systématique",
            slug="theologie-systematique",
        )
        assert str(d) == "Théologie systématique"
        assert d.slug == "theologie-systematique"

    def test_parcours_creation(self):
        from apps.formations.models import Parcours

        p = Parcours.objects.create(
            nom="Parcours diplômant ITEAG",
            slug="parcours-diplomant-iteag",
            type_parcours="diplomant_iteag",
            ects_requis=180,
        )
        assert str(p) == "Parcours diplômant ITEAG"
        assert p.type_parcours == "diplomant_iteag"
