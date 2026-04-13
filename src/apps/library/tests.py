import pytest
from django.test import Client
from django.urls import reverse

from apps.formations.models import Discipline
from apps.library.models import NoticeBibliographique


@pytest.fixture
def discipline(db):
    return Discipline.objects.create(nom="Ancien Testament", slug="ancien-testament")


@pytest.fixture
def notice(discipline):
    return NoticeBibliographique.objects.create(
        titre="Introduction à l'Ancien Testament",
        auteur="Raymond Dillard",
        editeur="Excelsis",
        isbn="978-2-755-0001",
        discipline=discipline,
        disponible=True,
    )


# ──────────────────────────────────────────────
# Model tests
# ──────────────────────────────────────────────


@pytest.mark.django_db
class TestNoticeBibliographique:
    def test_create(self, notice):
        assert notice.pk is not None
        assert notice.disponible is True

    def test_str_with_auteur(self, notice):
        assert "Dillard" in str(notice)
        assert "Ancien Testament" in str(notice)

    def test_str_without_auteur(self, discipline):
        n = NoticeBibliographique.objects.create(
            titre="Dictionnaire hébreu", discipline=discipline,
        )
        assert str(n) == "Dictionnaire hébreu"

    def test_ordering(self, discipline):
        NoticeBibliographique.objects.create(titre="ZZZ", discipline=discipline)
        NoticeBibliographique.objects.create(titre="AAA", discipline=discipline)
        notices = list(NoticeBibliographique.objects.all())
        assert notices[0].titre < notices[-1].titre


# ──────────────────────────────────────────────
# View tests
# ──────────────────────────────────────────────


@pytest.mark.django_db
class TestCatalogueView:
    def test_catalogue_get(self, client: Client):
        url = reverse("library:catalogue")
        response = client.get(url)
        assert response.status_code == 200

    def test_catalogue_search(self, client: Client, notice):
        url = reverse("library:catalogue")
        response = client.get(url, {"q": "Ancien"})
        assert response.status_code == 200

    def test_catalogue_filter_discipline(self, client: Client, notice, discipline):
        url = reverse("library:catalogue")
        response = client.get(url, {"discipline": discipline.pk})
        assert response.status_code == 200

    def test_catalogue_filter_disponible(self, client: Client, notice):
        url = reverse("library:catalogue")
        response = client.get(url, {"disponible": "1"})
        assert response.status_code == 200

    def test_notice_detail(self, client: Client, notice):
        url = reverse("library:notice_detail", kwargs={"pk": notice.pk})
        response = client.get(url)
        assert response.status_code == 200

    def test_notice_detail_404(self, client: Client):
        url = reverse("library:notice_detail", kwargs={"pk": 99999})
        response = client.get(url)
        assert response.status_code == 404

    def test_htmx_partial_response(self, client: Client):
        url = reverse("library:catalogue")
        response = client.get(url, HTTP_HX_REQUEST="true")
        assert response.status_code == 200
