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
            titre="Dictionnaire hébreu",
            discipline=discipline,
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

    @pytest.mark.parametrize(
        ("terme", "raison"),
        [
            ("TP-222", "la cote est ce qu'un bibliothécaire tape en premier"),
            ("Dillard", "chercher un auteur par son nom est le cas le plus courant"),
            ("978-2-755-0001", "l'ISBN identifie l'ouvrage sans ambiguïté"),
        ],
    )
    def test_le_catalogue_retrouve_une_notice_non_indexee(self, client: Client, notice, terme, raison):
        """Le vecteur plein texte n'est calculé qu'au `save()`.

        Une notice écrite en masse — import, chargement de données, migration —
        garde un vecteur nul et disparaissait alors de toute recherche, sans
        qu'aucune erreur ne le signale. La recherche ne doit donc pas dépendre
        du seul index.
        """
        notice.cote = "TP-222"
        notice.save()
        NoticeBibliographique.objects.filter(pk=notice.pk).update(search_vector=None)

        reponse = client.get(reverse("library:catalogue"), {"q": terme})

        assert reponse.status_code == 200
        assert notice in reponse.context["notices"], raison

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


@pytest.mark.django_db
class TestEmprunts:
    def test_reserver_ouvrage(self, notice):
        from datetime import timedelta

        from django.utils import timezone

        from apps.accounts.models import User
        from apps.library import services
        from apps.library.models import Emprunt

        user = User.objects.create_user(username="lecteur1", email="l1@iteag.org", password="password123")
        emprunt = services.reserver_ouvrage(notice, user)

        assert emprunt.statut == Emprunt.Statut.RESERVE
        assert emprunt.date_retour_prevue == timezone.localdate() + timedelta(days=21)
        notice.refresh_from_db()
        assert notice.disponible is False

    def test_reserver_ouvrage_deja_indisponible_refuse(self, notice):
        from django.core.exceptions import ValidationError

        from apps.accounts.models import User
        from apps.library import services

        user = User.objects.create_user(username="lecteur2", email="l2@iteag.org", password="password123")
        notice.disponible = False
        notice.save()

        with pytest.raises(ValidationError, match="déjà emprunté ou indisponible"):
            services.reserver_ouvrage(notice, user)

    def test_valider_retrait_et_restitution(self, notice):
        from apps.accounts.models import User
        from apps.library import services
        from apps.library.models import Emprunt

        user = User.objects.create_user(username="lecteur3", email="l3@iteag.org", password="password123")
        emprunt = services.reserver_ouvrage(notice, user)

        emprunt = services.valider_retrait(emprunt)
        assert emprunt.statut == Emprunt.Statut.EN_COURS
        assert emprunt.date_retrait is not None

        emprunt = services.restituer_ouvrage(emprunt, commentaire="Bon état")
        assert emprunt.statut == Emprunt.Statut.RENDU
        assert emprunt.commentaire == "Bon état"
        notice.refresh_from_db()
        assert notice.disponible is True

    def test_verifier_retards(self, notice):
        from datetime import timedelta

        from django.utils import timezone

        from apps.accounts.models import User
        from apps.library import services
        from apps.library.models import Emprunt

        user = User.objects.create_user(username="lecteur4", email="l4@iteag.org", password="password123")
        emprunt = services.reserver_ouvrage(notice, user)
        services.valider_retrait(emprunt)
        emprunt.date_retour_prevue = timezone.localdate() - timedelta(days=5)
        emprunt.save(update_fields=["date_retour_prevue"])

        retards = services.verifier_retards()
        assert retards == 1
        emprunt.refresh_from_db()
        assert emprunt.statut == Emprunt.Statut.EN_RETARD
