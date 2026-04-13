import pytest
from datetime import date, timedelta
from decimal import Decimal

from django.test import Client
from django.urls import reverse

from apps.accounts.models import User
from apps.formations.models import Cours, Discipline, Parcours, Professeur
from apps.academics.models import (
    CoursDeSession,
    CreditECTS,
    InscriptionSession,
    Paiement,
    ProfilEtudiant,
    Promotion,
    SessionAcademique,
)


@pytest.fixture
def discipline(db):
    return Discipline.objects.create(nom="Théologie systématique", slug="theologie-systematique")


@pytest.fixture
def parcours(db):
    return Parcours.objects.create(
        nom="Diplômant ITEAG", slug="diplomant-iteag",
        type_parcours="diplomant_iteag", ects_requis=180,
    )


@pytest.fixture
def promotion(parcours):
    return Promotion.objects.create(
        nom="Promotion 2024-2030", parcours=parcours,
        annee_debut=2024, annee_fin=2030,
    )


@pytest.fixture
def cours(discipline):
    return Cours.objects.create(
        titre="Évangile de Jean", slug="evangile-de-jean",
        discipline=discipline, ects=Decimal("2.5"),
    )


@pytest.fixture
def professeur(db):
    return Professeur.objects.create(
        nom="Martin", prenom="Pierre", slug="pierre-martin",
        specialite="Nouveau Testament",
    )


@pytest.fixture
def session_academique(db):
    today = date.today()
    return SessionAcademique.objects.create(
        nom="Session Pâques 2025", periode="paques",
        annee_academique="2024-2025",
        date_debut=today, date_fin=today + timedelta(days=7),
    )


@pytest.fixture
def etudiant_user(db):
    return User.objects.create_user(
        username="etudiant1", email="etudiant@iteag.org",
        password="pass123!", first_name="Jean", last_name="Petit",
        role="etudiant",
    )


@pytest.fixture
def profil_etudiant(etudiant_user, parcours, promotion):
    return ProfilEtudiant.objects.create(
        utilisateur=etudiant_user, parcours=parcours,
        promotion=promotion, numero_etudiant="ETU-001",
        statut_inscription="actif",
    )


@pytest.fixture
def cours_session(session_academique, cours, professeur):
    return CoursDeSession.objects.create(
        session=session_academique, cours=cours,
        enseignant=professeur, salle="A1",
    )


# ──────────────────────────────────────────────
# Model tests — Academics
# ──────────────────────────────────────────────


@pytest.mark.django_db
class TestPromotionModel:
    def test_create(self, promotion):
        assert promotion.pk is not None
        assert "2024" in str(promotion)

    def test_ordering(self, parcours):
        p1 = Promotion.objects.create(nom="P1", parcours=parcours, annee_debut=2020, annee_fin=2026)
        p2 = Promotion.objects.create(nom="P2", parcours=parcours, annee_debut=2022, annee_fin=2028)
        assert list(Promotion.objects.all())[0].annee_debut >= list(Promotion.objects.all())[1].annee_debut


@pytest.mark.django_db
class TestProfilEtudiantModel:
    def test_create(self, profil_etudiant):
        assert profil_etudiant.pk is not None
        assert profil_etudiant.numero_etudiant == "ETU-001"

    def test_str(self, profil_etudiant):
        assert "Jean Petit" in str(profil_etudiant)
        assert "ETU-001" in str(profil_etudiant)

    def test_total_ects_acquis_zero(self, profil_etudiant):
        assert profil_etudiant.total_ects_acquis == 0

    def test_ects_restants(self, profil_etudiant):
        assert profil_etudiant.ects_restants == 180

    def test_ects_with_credits(self, profil_etudiant, cours, session_academique):
        CreditECTS.objects.create(
            etudiant=profil_etudiant, cours=cours,
            session=session_academique, ects_obtenus=Decimal("2.5"),
            date_validation=date.today(),
        )
        assert profil_etudiant.total_ects_acquis == Decimal("2.5")
        assert profil_etudiant.ects_restants == Decimal("177.5")


@pytest.mark.django_db
class TestSessionAcademiqueModel:
    def test_create(self, session_academique):
        assert session_academique.pk is not None
        assert session_academique.statut == SessionAcademique.StatutSession.PLANIFIEE

    def test_str(self, session_academique):
        assert "2024-2025" in str(session_academique)

    def test_unique_together(self, session_academique):
        from django.db import IntegrityError
        with pytest.raises(IntegrityError):
            SessionAcademique.objects.create(
                nom="Doublon", periode="paques",
                annee_academique="2024-2025",
                date_debut=date.today(), date_fin=date.today(),
            )


@pytest.mark.django_db
class TestCoursDeSessionModel:
    def test_create(self, cours_session):
        assert cours_session.pk is not None
        assert cours_session.statut == CoursDeSession.StatutCours.PROGRAMME

    def test_str(self, cours_session):
        assert "Évangile de Jean" in str(cours_session)


@pytest.mark.django_db
class TestInscriptionSession:
    def test_create(self, profil_etudiant, cours_session):
        inscription = InscriptionSession.objects.create(
            etudiant=profil_etudiant, cours_session=cours_session,
        )
        assert inscription.pk is not None

    def test_unique_together(self, profil_etudiant, cours_session):
        InscriptionSession.objects.create(
            etudiant=profil_etudiant, cours_session=cours_session,
        )
        from django.db import IntegrityError
        with pytest.raises(IntegrityError):
            InscriptionSession.objects.create(
                etudiant=profil_etudiant, cours_session=cours_session,
            )


@pytest.mark.django_db
class TestPaiementModel:
    def test_create(self, profil_etudiant, session_academique):
        p = Paiement.objects.create(
            etudiant=profil_etudiant, session=session_academique,
            montant=Decimal("250.00"), date_paiement=date.today(),
            mode="virement",
        )
        assert p.pk is not None
        assert p.statut == Paiement.StatutPaiement.EN_ATTENTE

    def test_str(self, profil_etudiant, session_academique):
        p = Paiement.objects.create(
            etudiant=profil_etudiant, session=session_academique,
            montant=Decimal("250.00"), date_paiement=date.today(),
            mode="virement",
        )
        assert "250" in str(p)


# ──────────────────────────────────────────────
# View tests — Student portal (role-guarded)
# ──────────────────────────────────────────────


@pytest.mark.django_db
class TestStudentDashboardAccess:
    def test_anonymous_redirect(self, client: Client):
        url = reverse("academics:dashboard")
        response = client.get(url)
        assert response.status_code == 302
        assert "connexion" in response.url or "login" in response.url

    def test_student_access(self, client: Client, profil_etudiant):
        client.force_login(profil_etudiant.utilisateur)
        url = reverse("academics:dashboard")
        response = client.get(url)
        assert response.status_code == 200

    def test_non_student_denied(self, client: Client, db):
        staff = User.objects.create_user(
            username="staff_no_student", email="staff@t.org",
            password="pass!", role="admin",
        )
        client.force_login(staff)
        url = reverse("academics:dashboard")
        response = client.get(url)
        assert response.status_code == 403

    def test_progress_view(self, client: Client, profil_etudiant):
        client.force_login(profil_etudiant.utilisateur)
        url = reverse("academics:progress")
        response = client.get(url)
        assert response.status_code == 200

    def test_courses_view(self, client: Client, profil_etudiant):
        client.force_login(profil_etudiant.utilisateur)
        url = reverse("academics:courses")
        response = client.get(url)
        assert response.status_code == 200

    def test_grades_view(self, client: Client, profil_etudiant):
        client.force_login(profil_etudiant.utilisateur)
        url = reverse("academics:grades")
        response = client.get(url)
        assert response.status_code == 200


# ──────────────────────────────────────────────
# View tests — Teacher portal (role-guarded)
# ──────────────────────────────────────────────


@pytest.mark.django_db
class TestTeacherPortalAccess:
    def test_anonymous_redirect(self, client: Client):
        url = reverse("lms:dashboard")
        response = client.get(url)
        assert response.status_code == 302

    def test_teacher_access(self, client: Client, professeur):
        teacher_user = User.objects.create_user(
            username="enseignant1", email="teach@iteag.org",
            password="pass!", role="enseignant",
        )
        professeur.user = teacher_user
        professeur.save()
        client.force_login(teacher_user)
        url = reverse("lms:dashboard")
        response = client.get(url)
        assert response.status_code == 200

    def test_student_denied(self, client: Client, profil_etudiant):
        client.force_login(profil_etudiant.utilisateur)
        url = reverse("lms:dashboard")
        response = client.get(url)
        assert response.status_code == 403

    def test_courses_list(self, client: Client, professeur):
        teacher_user = User.objects.create_user(
            username="enseignant2", email="teach2@iteag.org",
            password="pass!", role="enseignant",
        )
        professeur.user = teacher_user
        professeur.save()
        client.force_login(teacher_user)
        url = reverse("lms:courses_list")
        response = client.get(url)
        assert response.status_code == 200


# ──────────────────────────────────────────────
# View tests — Documents (student role-guarded)
# ──────────────────────────────────────────────


@pytest.mark.django_db
class TestDocumentViews:
    def test_anonymous_redirect(self, client: Client):
        url = reverse("documents:list")
        response = client.get(url)
        assert response.status_code == 302

    def test_student_list(self, client: Client, profil_etudiant):
        client.force_login(profil_etudiant.utilisateur)
        url = reverse("documents:list")
        response = client.get(url)
        assert response.status_code == 200

    def test_generate_invalid_type(self, client: Client, profil_etudiant):
        client.force_login(profil_etudiant.utilisateur)
        url = reverse("documents:generate", kwargs={"document_type": "inexistant"})
        response = client.get(url)
        assert response.status_code == 404
