import pytest
from django.core import mail
from django.test import Client
from django.urls import reverse

from apps.accounts.models import User
from apps.admissions.forms import CandidatureForm
from apps.admissions.models import DossierCandidature, HistoriqueStatut
from apps.formations.models import Parcours


@pytest.fixture
def parcours(db):
    return Parcours.objects.create(
        nom="Parcours diplômant ITEAG",
        slug="parcours-diplomant-iteag",
        type_parcours="diplomant_iteag",
        ects_requis=180,
    )


@pytest.fixture
def dossier(parcours):
    return DossierCandidature.objects.create(
        nom="Dupont",
        prenom="Marie",
        email="marie@example.org",
        telephone="0690000000",
        parcours_souhaite=parcours,
        motivations="Test de motivation.",
    )


@pytest.fixture
def staff_user(db):
    return User.objects.create_user(
        username="staff",
        email="staff@iteag.org",
        password="staffpass123!",
        role="admin",
        is_staff=True,
    )


# ──────────────────────────────────────────────
# Model tests
# ──────────────────────────────────────────────


@pytest.mark.django_db
class TestDossierCandidatureModel:
    def test_create_dossier(self, dossier):
        assert dossier.pk is not None
        assert dossier.statut == DossierCandidature.Statut.SOUMIS

    def test_token_generated(self, dossier):
        assert dossier.token_suivi
        assert len(dossier.token_suivi) > 30

    def test_nom_complet(self, dossier):
        assert dossier.nom_complet == "Marie Dupont"

    def test_str_representation(self, dossier):
        assert "Marie" in str(dossier)
        assert "Dupont" in str(dossier)

    def test_default_ordering(self, parcours):
        d1 = DossierCandidature.objects.create(
            nom="A", prenom="A", email="a@a.org",
            parcours_souhaite=parcours, motivations=".",
        )
        d2 = DossierCandidature.objects.create(
            nom="B", prenom="B", email="b@b.org",
            parcours_souhaite=parcours, motivations=".",
        )
        dossiers = list(DossierCandidature.objects.all())
        assert dossiers[0].pk == d2.pk  # most recent first

    def test_status_choices(self):
        assert len(DossierCandidature.Statut.choices) == 5


@pytest.mark.django_db
class TestHistoriqueStatut:
    def test_create_historique(self, dossier, staff_user):
        h = HistoriqueStatut.objects.create(
            dossier=dossier,
            ancien_statut=DossierCandidature.Statut.SOUMIS,
            nouveau_statut=DossierCandidature.Statut.EN_EXAMEN,
            modifie_par=staff_user,
            commentaire="Passage en examen.",
        )
        assert h.pk is not None
        assert dossier.historique.count() == 1


# ──────────────────────────────────────────────
# Form tests
# ──────────────────────────────────────────────


@pytest.mark.django_db
class TestCandidatureForm:
    def test_valid_form(self, parcours):
        data = {
            "nom": "Test",
            "prenom": "User",
            "email": "test@example.org",
            "parcours_souhaite": parcours.pk,
            "motivations": "Ma motivation.",
            "honeypot": "",
        }
        form = CandidatureForm(data=data)
        assert form.is_valid(), form.errors

    def test_honeypot_rejects(self, parcours):
        data = {
            "nom": "Bot",
            "prenom": "Spam",
            "email": "bot@spam.org",
            "parcours_souhaite": parcours.pk,
            "motivations": "Spam.",
            "honeypot": "gotcha",
        }
        form = CandidatureForm(data=data)
        assert not form.is_valid()
        assert "honeypot" in form.errors

    def test_missing_required_fields(self):
        form = CandidatureForm(data={})
        assert not form.is_valid()
        for field in ["nom", "prenom", "email", "parcours_souhaite", "motivations"]:
            assert field in form.errors


# ──────────────────────────────────────────────
# View tests
# ──────────────────────────────────────────────


@pytest.mark.django_db
class TestCandidatureViews:
    def test_form_get(self, client: Client):
        url = reverse("admissions:candidature_form")
        response = client.get(url)
        assert response.status_code == 200

    def test_form_post_valid(self, client: Client, parcours):
        url = reverse("admissions:candidature_form")
        data = {
            "nom": "Martin",
            "prenom": "Paul",
            "email": "paul@example.org",
            "parcours_souhaite": parcours.pk,
            "motivations": "Ma motivation.",
            "honeypot": "",
        }
        response = client.post(url, data)
        assert response.status_code == 302  # redirect
        assert DossierCandidature.objects.filter(email="paul@example.org").exists()
        assert len(mail.outbox) == 1  # confirmation email

    def test_form_post_honeypot(self, client: Client, parcours):
        url = reverse("admissions:candidature_form")
        data = {
            "nom": "Bot",
            "prenom": "Bad",
            "email": "bot@spam.org",
            "parcours_souhaite": parcours.pk,
            "motivations": "Spam",
            "honeypot": "filled_by_bot",
        }
        response = client.post(url, data)
        assert response.status_code == 200  # re-renders form
        assert DossierCandidature.objects.filter(email="bot@spam.org").count() == 0

    def test_confirmation_view(self, client: Client, dossier):
        url = reverse("admissions:candidature_confirmation", kwargs={"token": dossier.token_suivi})
        response = client.get(url)
        assert response.status_code == 200

    def test_suivi_view(self, client: Client, dossier):
        url = reverse("admissions:candidature_suivi", kwargs={"token": dossier.token_suivi})
        response = client.get(url)
        assert response.status_code == 200

    def test_suivi_invalid_token(self, client: Client):
        url = reverse("admissions:candidature_suivi", kwargs={"token": "invalid-token"})
        response = client.get(url)
        assert response.status_code == 404

    def test_parcours_preview_htmx(self, client: Client, parcours):
        url = reverse("admissions:parcours_preview")
        response = client.get(url, {"parcours": parcours.pk})
        assert response.status_code == 200
