import pytest
from datetime import date, timedelta
from decimal import Decimal

from django.test import Client
from django.urls import reverse

from apps.accounts.models import User
from apps.academics.models import Paiement, ProfilEtudiant, Promotion, SessionAcademique
from apps.admissions.models import DossierCandidature
from apps.formations.models import Parcours


@pytest.fixture
def staff_user(db):
    return User.objects.create_user(
        username="admin_staff", email="admin@iteag.org",
        password="pass123!", role="admin", is_staff=True,
    )


@pytest.fixture
def parcours(db):
    return Parcours.objects.create(
        nom="Diplômant", slug="diplomant",
        type_parcours="diplomant_iteag", ects_requis=180,
    )


@pytest.fixture
def promotion(parcours):
    return Promotion.objects.create(
        nom="P2024", parcours=parcours,
        annee_debut=2024, annee_fin=2030,
    )


@pytest.fixture
def dossier(parcours):
    return DossierCandidature.objects.create(
        nom="Test", prenom="Export", email="export@t.org",
        parcours_souhaite=parcours, motivations=".",
    )


@pytest.fixture
def etudiant(db, parcours, promotion):
    u = User.objects.create_user(
        username="etu_export", email="etu@t.org", password="pass!",
        first_name="Etu", last_name="Export", role="etudiant",
    )
    return ProfilEtudiant.objects.create(
        utilisateur=u, parcours=parcours, promotion=promotion,
        numero_etudiant="ETU-EXP-001", statut_inscription="actif",
    )


@pytest.fixture
def session_acad(db):
    today = date.today()
    return SessionAcademique.objects.create(
        nom="S1", periode="paques", annee_academique="2024-2025",
        date_debut=today, date_fin=today + timedelta(days=7),
    )


# ──────────────────────────────────────────────
# Admin auth guard
# ──────────────────────────────────────────────


@pytest.mark.django_db
class TestAdminAuthGuard:
    def test_dashboard_anonymous_redirect(self, client: Client):
        url = reverse("administration:dashboard")
        response = client.get(url)
        assert response.status_code == 302

    def test_dashboard_student_denied(self, client: Client, etudiant):
        client.force_login(etudiant.utilisateur)
        url = reverse("administration:dashboard")
        response = client.get(url)
        assert response.status_code == 403

    def test_dashboard_staff_access(self, client: Client, staff_user):
        client.force_login(staff_user)
        url = reverse("administration:dashboard")
        response = client.get(url)
        assert response.status_code == 200


# ──────────────────────────────────────────────
# CSV Exports
# ──────────────────────────────────────────────


@pytest.mark.django_db
class TestCsvExports:
    def test_export_candidatures_csv(self, client: Client, staff_user, dossier):
        client.force_login(staff_user)
        url = reverse("administration:export_candidatures")
        response = client.get(url)
        assert response.status_code == 200
        assert response["Content-Type"] == "text/csv"
        assert "candidatures.csv" in response["Content-Disposition"]
        content = response.content.decode("utf-8-sig")
        assert "Test" in content
        assert "Export" in content

    def test_export_candidatures_filter(self, client: Client, staff_user, dossier):
        client.force_login(staff_user)
        url = reverse("administration:export_candidatures")
        response = client.get(url, {"statut": "soumis"})
        assert response.status_code == 200
        content = response.content.decode("utf-8-sig")
        assert "Test" in content

    def test_export_etudiants_csv(self, client: Client, staff_user, etudiant):
        client.force_login(staff_user)
        url = reverse("administration:export_etudiants")
        response = client.get(url)
        assert response.status_code == 200
        assert "etudiants.csv" in response["Content-Disposition"]
        content = response.content.decode("utf-8-sig")
        assert "ETU-EXP-001" in content

    def test_export_paiements_csv(self, client: Client, staff_user, etudiant, session_acad):
        Paiement.objects.create(
            etudiant=etudiant, session=session_acad,
            montant=Decimal("250.00"), date_paiement=date.today(),
            mode="virement",
        )
        client.force_login(staff_user)
        url = reverse("administration:export_paiements")
        response = client.get(url)
        assert response.status_code == 200
        assert "paiements.csv" in response["Content-Disposition"]
        content = response.content.decode("utf-8-sig")
        assert "250" in content

    def test_export_requires_staff(self, client: Client, etudiant):
        client.force_login(etudiant.utilisateur)
        for name in ["export_candidatures", "export_etudiants", "export_paiements"]:
            url = reverse(f"administration:{name}")
            response = client.get(url)
            assert response.status_code == 403


# ──────────────────────────────────────────────
# Bulk status change
# ──────────────────────────────────────────────


@pytest.mark.django_db
class TestBulkCandidatureStatus:
    def test_bulk_status_change(self, client: Client, staff_user, dossier):
        client.force_login(staff_user)
        url = reverse("administration:candidatures_bulk_status")
        response = client.post(url, {
            "selected": [dossier.pk],
            "bulk_statut": "en_examen",
        })
        assert response.status_code == 302
        dossier.refresh_from_db()
        assert dossier.statut == "en_examen"
        assert dossier.historique.count() == 1

    def test_bulk_no_selection(self, client: Client, staff_user):
        client.force_login(staff_user)
        url = reverse("administration:candidatures_bulk_status")
        response = client.post(url, {"bulk_statut": "en_examen"})
        assert response.status_code == 302  # redirect with warning

    def test_bulk_invalid_statut(self, client: Client, staff_user, dossier):
        client.force_login(staff_user)
        url = reverse("administration:candidatures_bulk_status")
        response = client.post(url, {
            "selected": [dossier.pk],
            "bulk_statut": "invalide",
        })
        assert response.status_code == 302
        dossier.refresh_from_db()
        assert dossier.statut == "soumis"  # unchanged

    def test_bulk_requires_staff(self, client: Client, etudiant, dossier):
        client.force_login(etudiant.utilisateur)
        url = reverse("administration:candidatures_bulk_status")
        response = client.post(url, {
            "selected": [dossier.pk],
            "bulk_statut": "en_examen",
        })
        assert response.status_code == 403


# ──────────────────────────────────────────────
# Admin list views
# ──────────────────────────────────────────────


@pytest.mark.django_db
class TestAdminListViews:
    def test_candidatures_list(self, client: Client, staff_user, dossier):
        client.force_login(staff_user)
        url = reverse("administration:candidatures")
        response = client.get(url)
        assert response.status_code == 200

    def test_candidature_detail(self, client: Client, staff_user, dossier):
        client.force_login(staff_user)
        url = reverse("administration:candidature_detail", kwargs={"pk": dossier.pk})
        response = client.get(url)
        assert response.status_code == 200

    def test_etudiants_list(self, client: Client, staff_user, etudiant):
        client.force_login(staff_user)
        url = reverse("administration:etudiants")
        response = client.get(url)
        assert response.status_code == 200

    def test_professeurs_list(self, client: Client, staff_user):
        client.force_login(staff_user)
        url = reverse("administration:professeurs")
        response = client.get(url)
        assert response.status_code == 200

    def test_formations_list(self, client: Client, staff_user):
        client.force_login(staff_user)
        url = reverse("administration:formations")
        response = client.get(url)
        assert response.status_code == 200

    def test_sessions_list(self, client: Client, staff_user):
        client.force_login(staff_user)
        url = reverse("administration:sessions")
        response = client.get(url)
        assert response.status_code == 200

    def test_utilisateurs_list(self, client: Client, staff_user):
        client.force_login(staff_user)
        url = reverse("administration:utilisateurs")
        response = client.get(url)
        assert response.status_code == 200

    def test_candidatures_search(self, client: Client, staff_user, dossier):
        client.force_login(staff_user)
        url = reverse("administration:candidatures")
        response = client.get(url, {"q": "Test"})
        assert response.status_code == 200

    def test_candidatures_filter(self, client: Client, staff_user, dossier):
        client.force_login(staff_user)
        url = reverse("administration:candidatures")
        response = client.get(url, {"statut": "soumis"})
        assert response.status_code == 200
