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

    def test_cours_bibliographie(self, client: Client):
        from apps.formations.models import Cours, Discipline
        from apps.library.models import NoticeBibliographique

        d = Discipline.objects.create(nom="Nouveau Testament", slug="nouveau-testament")
        c = Cours.objects.create(titre="Épîtres pauliennes", slug="epitres-pauliennes", discipline=d)
        notice = NoticeBibliographique.objects.create(
            titre="Commentaire aux Romains", auteur="F.F. Bruce", cote="NT-101"
        )
        c.bibliographie.add(notice)

        assert c.bibliographie.count() == 1
        assert notice.cours_recommandant.first() == c

        url = reverse("formations:cours_detail", kwargs={"slug": c.slug})
        resp = client.get(url)
        assert resp.status_code == 200
        assert "Commentaire aux Romains" in resp.content.decode()
