"""
Tests du référentiel pilotable : promotions, grille tarifaire, crédits ECTS.

Ces trois modèles n'avaient aucun chemin d'écriture dans l'application. Le plus
gênant était la promotion : l'admission en exige une, et la liste ne pouvait
être remplie que depuis l'administration Django.

Les tests vérifient autant le partage des rôles que le CRUD — le secrétariat
doit pouvoir tenir le dossier des étudiants sans pouvoir toucher aux tarifs.
"""

import pytest
from django.urls import reverse

from apps.academics.models import CreditECTS, ProfilEtudiant, Promotion, SessionAcademique
from apps.accounts.models import User
from apps.formations.models import Cours, Discipline, Parcours, Tarif


@pytest.fixture
def parcours(db):
    return Parcours.objects.create(
        nom="Diplômant", slug="diplomant-ref", type_parcours=Parcours.TypeParcours.DIPLOMANT_ITEAG
    )


@pytest.fixture
def admin(db):
    return User.objects.create_user(
        username="admin_ref", email="admin_ref@iteag.org", password="motdepasse-long-12", role=User.Role.ADMIN
    )


@pytest.fixture
def secretaire(db):
    return User.objects.create_user(
        username="secretaire_ref",
        email="secretaire_ref@iteag.org",
        password="motdepasse-long-12",
        role=User.Role.SECRETARIAT,
    )


@pytest.fixture
def etudiant(db, parcours):
    utilisateur = User.objects.create_user(
        username="etu_ref",
        email="etu_ref@iteag.org",
        password="motdepasse-long-12",
        first_name="Paul",
        last_name="Sainte-Rose",
        role=User.Role.ETUDIANT,
    )
    promotion = Promotion.objects.create(nom="Promo réf", parcours=parcours, annee_debut=2026, annee_fin=2032)
    return ProfilEtudiant.objects.create(
        utilisateur=utilisateur, parcours=parcours, promotion=promotion, numero_etudiant="ETU-REF-001"
    )


@pytest.mark.django_db
class TestPromotions:
    def test_le_secretariat_cree_une_promotion(self, client, secretaire, parcours):
        """C'est la condition pour qu'une candidature puisse être acceptée."""
        client.force_login(secretaire)
        client.post(
            reverse("administration:promotion_create"),
            {"nom": "Promotion 2027-2033", "parcours": parcours.pk, "annee_debut": 2027, "annee_fin": 2033},
        )
        assert Promotion.objects.filter(nom="Promotion 2027-2033").exists()

    def test_la_liste_repond(self, client, secretaire):
        client.force_login(secretaire)
        assert client.get(reverse("administration:promotions")).status_code == 200

    def test_une_annee_de_fin_anterieure_est_refusee(self, client, secretaire, parcours):
        client.force_login(secretaire)
        reponse = client.post(
            reverse("administration:promotion_create"),
            {"nom": "Promotion absurde", "parcours": parcours.pk, "annee_debut": 2030, "annee_fin": 2025},
        )
        assert reponse.status_code == 200
        assert not Promotion.objects.filter(nom="Promotion absurde").exists()

    def test_modification(self, client, secretaire, parcours):
        promotion = Promotion.objects.create(
            nom="Promo à corriger", parcours=parcours, annee_debut=2026, annee_fin=2032
        )
        client.force_login(secretaire)
        client.post(
            reverse("administration:promotion_update", kwargs={"pk": promotion.pk}),
            {"nom": "Promo corrigée", "parcours": parcours.pk, "annee_debut": 2026, "annee_fin": 2032},
        )
        promotion.refresh_from_db()
        assert promotion.nom == "Promo corrigée"

    def test_une_promotion_peuplee_ne_se_supprime_pas(self, client, admin, etudiant):
        """La clé est en PROTECT : mieux vaut expliquer que laisser remonter une erreur de base."""
        promotion = etudiant.promotion
        client.force_login(admin)
        client.post(reverse("administration:promotion_delete", kwargs={"pk": promotion.pk}))
        assert Promotion.objects.filter(pk=promotion.pk).exists()

    def test_une_promotion_vide_se_supprime(self, client, admin, parcours):
        promotion = Promotion.objects.create(nom="Promo vide", parcours=parcours, annee_debut=2026, annee_fin=2032)
        client.force_login(admin)
        client.post(reverse("administration:promotion_delete", kwargs={"pk": promotion.pk}))
        assert not Promotion.objects.filter(pk=promotion.pk).exists()

    def test_un_etudiant_est_refuse(self, client, etudiant):
        client.force_login(etudiant.utilisateur)
        assert client.get(reverse("administration:promotions")).status_code in (302, 403)


@pytest.mark.django_db
class TestGrilleTarifaire:
    def test_l_administration_cree_un_tarif(self, client, admin):
        client.force_login(admin)
        client.post(
            reverse("administration:tarif_create"),
            {
                "formule": Tarif.FormuleTarif.TOUTES_SESSIONS,
                "type_membre": Tarif.TypeMembre.AUTRE,
                "montant_session": "180.00",
                "actif": "on",
            },
        )
        assert Tarif.objects.filter(montant_session="180.00").exists()

    def test_le_secretariat_consulte_mais_ne_cree_pas(self, client, secretaire):
        """Le tarif est affiché au public : la décision appartient à l'administration."""
        client.force_login(secretaire)
        assert client.get(reverse("administration:tarifs")).status_code == 200
        assert client.get(reverse("administration:tarif_create")).status_code in (302, 403)

    def test_modification(self, client, admin):
        tarif = Tarif.objects.create(
            formule=Tarif.FormuleTarif.SESSION_CHOIX,
            type_membre=Tarif.TypeMembre.EGLISE_FONDATRICE,
            montant_session="100.00",
        )
        client.force_login(admin)
        client.post(
            reverse("administration:tarif_update", kwargs={"pk": tarif.pk}),
            {"formule": tarif.formule, "type_membre": tarif.type_membre, "montant_session": "120.00", "actif": "on"},
        )
        tarif.refresh_from_db()
        assert str(tarif.montant_session) == "120.00"


@pytest.mark.django_db
class TestCreditsECTS:
    @pytest.fixture
    def cours(self, db):
        discipline = Discipline.objects.create(nom="Histoire", slug="histoire-ref")
        return Cours.objects.create(titre="Histoire de l'Église", slug="histoire-eglise", discipline=discipline)

    @pytest.fixture
    def session(self, db):
        return SessionAcademique.objects.create(
            nom="Session de Carnaval",
            periode=SessionAcademique.Periode.CARNAVAL,
            annee_academique="2026-2027",
            date_debut="2027-02-15",
            date_fin="2027-02-20",
        )

    def test_le_secretariat_porte_un_credit_flte(self, client, secretaire, etudiant):
        """Le suivi croisé ITEAG/FLTE est une exigence du CDC : il faut pouvoir saisir l'externe."""
        client.force_login(secretaire)
        client.post(
            reverse("administration:credit_ects_create"),
            {
                "etudiant": etudiant.pk,
                "ects_obtenus": "5",
                "source": CreditECTS.SourceCredit.FLTE,
                "date_validation": "2026-06-30",
            },
        )
        credit = CreditECTS.objects.get(etudiant=etudiant)
        assert credit.source == CreditECTS.SourceCredit.FLTE
        assert float(credit.ects_obtenus) == 5

    def test_un_credit_nul_est_refuse(self, client, secretaire, etudiant):
        client.force_login(secretaire)
        client.post(
            reverse("administration:credit_ects_create"),
            {
                "etudiant": etudiant.pk,
                "ects_obtenus": "0",
                "source": CreditECTS.SourceCredit.FLTE,
                "date_validation": "2026-06-30",
            },
        )
        assert not CreditECTS.objects.filter(etudiant=etudiant).exists()

    def test_le_doublon_est_annonce_avant_la_contrainte(self, client, secretaire, etudiant, cours, session):
        """Une violation de contrainte brute n'aiderait personne au guichet."""
        CreditECTS.objects.create(
            etudiant=etudiant,
            cours=cours,
            session=session,
            ects_obtenus="2.5",
            source=CreditECTS.SourceCredit.ITEAG,
            date_validation="2027-02-20",
        )
        client.force_login(secretaire)
        reponse = client.post(
            reverse("administration:credit_ects_create"),
            {
                "etudiant": etudiant.pk,
                "cours": cours.pk,
                "session": session.pk,
                "ects_obtenus": "2.5",
                "source": CreditECTS.SourceCredit.ITEAG,
                "date_validation": "2027-02-20",
            },
        )
        assert reponse.status_code == 200
        assert "déjà crédité" in reponse.content.decode()
        assert CreditECTS.objects.filter(etudiant=etudiant).count() == 1

    def test_le_retrait_est_reserve_a_l_administration(self, client, secretaire, etudiant):
        credit = CreditECTS.objects.create(
            etudiant=etudiant, ects_obtenus="3", source=CreditECTS.SourceCredit.FLTE, date_validation="2026-06-30"
        )
        client.force_login(secretaire)
        assert client.post(reverse("administration:credit_ects_delete", kwargs={"pk": credit.pk})).status_code in (
            302,
            403,
        )
        assert CreditECTS.objects.filter(pk=credit.pk).exists()

    def test_le_retrait_par_l_administration_est_journalise(self, client, admin, etudiant):
        """Retirer un crédit modifie un dossier académique : la trace n'est pas optionnelle."""
        from apps.core.models import JournalAudit

        credit = CreditECTS.objects.create(
            etudiant=etudiant, ects_obtenus="3", source=CreditECTS.SourceCredit.FLTE, date_validation="2026-06-30"
        )
        client.force_login(admin)
        client.post(reverse("administration:credit_ects_delete", kwargs={"pk": credit.pk}))
        assert not CreditECTS.objects.filter(pk=credit.pk).exists()
        assert JournalAudit.objects.filter(action="suppression").exists()

    def test_la_liste_repond_et_filtre(self, client, secretaire, etudiant):
        CreditECTS.objects.create(
            etudiant=etudiant, ects_obtenus="3", source=CreditECTS.SourceCredit.FLTE, date_validation="2026-06-30"
        )
        client.force_login(secretaire)
        reponse = client.get(reverse("administration:credits_ects"), {"source": CreditECTS.SourceCredit.FLTE})
        assert reponse.status_code == 200
        assert "Sainte-Rose" in reponse.content.decode()
