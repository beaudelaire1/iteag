"""
Disciplines et parcours : le référentiel se tenait hors de l'application.

Les deux modèles fondent tout le reste — un cours appartient à une discipline,
un étudiant suit un parcours — et pourtant ni l'un ni l'autre n'avait de
chemin d'écriture ailleurs que dans l'administration Django. Ces cas fixent le
CRUD et, surtout, ce que la suppression doit refuser.
"""

import pytest
from django.urls import reverse

from apps.academics.models import ProfilEtudiant, Promotion
from apps.accounts.models import User
from apps.formations.models import Cours, Discipline, Parcours


@pytest.fixture
def secretaire(db):
    return User.objects.create_user(
        username="secretaire_form",
        email="secretaire_form@iteag.org",
        password="motdepasse-long-12",
        role=User.Role.SECRETARIAT,
    )


@pytest.fixture
def discipline(db):
    return Discipline.objects.create(nom="Patrologie", slug="patrologie-form")


@pytest.fixture
def parcours(db):
    return Parcours.objects.create(
        nom="Diplômant", slug="diplomant-form", type_parcours=Parcours.TypeParcours.DIPLOMANT_ITEAG
    )


@pytest.mark.django_db
class TestLesDisciplinesSeTiennentDansLApplication:
    def test_creation(self, client, secretaire):
        client.force_login(secretaire)
        reponse = client.post(
            reverse("administration:discipline_create"),
            {"nom": "Théologie pratique", "slug": "", "description": "", "ordre": 3},
        )
        assert reponse.status_code == 302
        # Le slug se déduit du nom : le secrétariat nomme, il n'invente pas d'adresse.
        assert Discipline.objects.get(nom="Théologie pratique").slug == "theologie-pratique"

    def test_modification(self, client, secretaire, discipline):
        client.force_login(secretaire)
        client.post(
            reverse("administration:discipline_update", args=[discipline.pk]),
            {"nom": "Patrologie grecque", "slug": discipline.slug, "description": "", "ordre": 1},
        )
        discipline.refresh_from_db()
        assert discipline.nom == "Patrologie grecque"

    def test_une_discipline_vide_se_supprime(self, client, secretaire, discipline):
        client.force_login(secretaire)
        client.post(reverse("administration:discipline_delete", args=[discipline.pk]), follow=True)
        assert not Discipline.objects.filter(pk=discipline.pk).exists()

    def test_une_discipline_qui_porte_des_cours_est_protegee(self, client, secretaire, discipline):
        """« Cours.discipline » est en PROTECT : le refus vaut mieux qu'une erreur de base."""
        client.force_login(secretaire)
        Cours.objects.create(titre="Les Pères", slug="les-peres-form", discipline=discipline)

        reponse = client.post(reverse("administration:discipline_delete", args=[discipline.pk]), follow=True)

        assert Discipline.objects.filter(pk=discipline.pk).exists()
        assert "rattachez-les" in reponse.content.decode().lower()

    def test_la_page_formations_mene_aux_ecrans_d_edition(self, client, secretaire, discipline):
        client.force_login(secretaire)
        contenu = client.get(reverse("administration:formations")).content.decode()
        assert reverse("administration:discipline_update", args=[discipline.pk]) in contenu
        assert reverse("administration:discipline_create") in contenu


@pytest.mark.django_db
class TestLesParcoursSeTiennentDansLApplication:
    def _donnees(self, **extra):
        base = {
            "nom": "Bachelor FLTE",
            "slug": "",
            "type_parcours": Parcours.TypeParcours.BACHELOR_FLTE,
            "description": "",
            "conditions_entree": "",
            "ects_requis": 180,
            "duree_annees": 3,
            "actif": "on",
            "meta_description": "",
        }
        return {**base, **extra}

    def test_creation(self, client, secretaire):
        client.force_login(secretaire)
        reponse = client.post(reverse("administration:parcours_create"), self._donnees())
        assert reponse.status_code == 302
        assert Parcours.objects.get(nom="Bachelor FLTE").slug == "bachelor-flte"

    def test_modification(self, client, secretaire, parcours):
        client.force_login(secretaire)
        client.post(
            reverse("administration:parcours_update", args=[parcours.pk]),
            self._donnees(nom="Diplômant ITEAG", slug=parcours.slug, duree_annees=6),
        )
        parcours.refresh_from_db()
        assert parcours.nom == "Diplômant ITEAG"
        assert parcours.duree_annees == 6

    def test_un_parcours_libre_se_supprime(self, client, secretaire, parcours):
        client.force_login(secretaire)
        client.post(reverse("administration:parcours_delete", args=[parcours.pk]), follow=True)
        assert not Parcours.objects.filter(pk=parcours.pk).exists()

    def test_un_parcours_suivi_par_un_etudiant_est_protege(self, client, secretaire, parcours):
        """Le parcours d'un étudiant est son diplôme : il se désactive, il ne s'efface pas."""
        client.force_login(secretaire)
        promotion = Promotion.objects.create(nom="Promo form", parcours=parcours, annee_debut=2026, annee_fin=2032)
        utilisateur = User.objects.create_user(
            username="etu_form", email="etu_form@iteag.org", password="motdepasse-long-12", role=User.Role.ETUDIANT
        )
        ProfilEtudiant.objects.create(
            utilisateur=utilisateur, parcours=parcours, promotion=promotion, numero_etudiant="ETU-FORM-1"
        )

        reponse = client.post(reverse("administration:parcours_delete", args=[parcours.pk]), follow=True)

        assert Parcours.objects.filter(pk=parcours.pk).exists()
        assert "décochez « actif »" in reponse.content.decode().lower()

    def test_un_parcours_portant_une_promotion_est_protege(self, client, secretaire, parcours):
        client.force_login(secretaire)
        Promotion.objects.create(nom="Promo seule", parcours=parcours, annee_debut=2026, annee_fin=2032)

        reponse = client.post(reverse("administration:parcours_delete", args=[parcours.pk]), follow=True)

        assert Parcours.objects.filter(pk=parcours.pk).exists()
        assert "promotions" in reponse.content.decode().lower()


@pytest.mark.django_db
def test_un_etudiant_n_atteint_pas_le_referentiel(client, db, discipline):
    utilisateur = User.objects.create_user(
        username="intrus_form", email="intrus_form@iteag.org", password="motdepasse-long-12", role=User.Role.ETUDIANT
    )
    client.force_login(utilisateur)
    for route, args in [
        ("administration:discipline_create", []),
        ("administration:discipline_update", [discipline.pk]),
        ("administration:parcours_create", []),
    ]:
        assert client.get(reverse(route, args=args)).status_code in (302, 403)
