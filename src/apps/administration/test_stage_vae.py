"""
Tests des stages et de la validation des acquis.

Le partage suit la décision de la maîtrise d'ouvrage : le stage est tenu par le
secrétariat, la VAE relève de l'administration seule.

L'enjeu technique dépasse le CRUD. Un stage validé vaut 30 ECTS, une VAE
accordée en vaut autant qu'accordé : si ces décisions ne rejoignent pas
`CreditECTS`, le relevé de l'étudiant diverge silencieusement de la réalité —
exactement le défaut qui existait entre la notation et les crédits.
"""

import pytest
from django.urls import reverse

from apps.academics.models import VAE, CreditECTS, ProfilEtudiant, Promotion, Stage
from apps.accounts.models import User
from apps.core.models import Notification
from apps.formations.models import Parcours


@pytest.fixture
def parcours(db):
    return Parcours.objects.create(
        nom="Diplômant", slug="diplomant-sv", type_parcours=Parcours.TypeParcours.DIPLOMANT_ITEAG, ects_requis=180
    )


@pytest.fixture
def admin(db):
    return User.objects.create_user(
        username="admin_sv", email="admin_sv@iteag.org", password="motdepasse-long-12", role=User.Role.ADMIN
    )


@pytest.fixture
def secretaire(db):
    return User.objects.create_user(
        username="secretaire_sv",
        email="secretaire_sv@iteag.org",
        password="motdepasse-long-12",
        role=User.Role.SECRETARIAT,
    )


@pytest.fixture
def etudiant(db, parcours):
    utilisateur = User.objects.create_user(
        username="etu_sv",
        email="etu_sv@iteag.org",
        password="motdepasse-long-12",
        first_name="Marie",
        last_name="Céleste",
        role=User.Role.ETUDIANT,
    )
    promotion = Promotion.objects.create(nom="Promo SV", parcours=parcours, annee_debut=2026, annee_fin=2032)
    return ProfilEtudiant.objects.create(
        utilisateur=utilisateur, parcours=parcours, promotion=promotion, numero_etudiant="ETU-SV-001"
    )


def champs_stage(etudiant, statut=Stage.StatutStage.EN_COURS, ects="30"):
    return {
        "etudiant": etudiant.pk,
        "type_stage": "Stage pastoral",
        "lieu": "Église de Fort-de-France",
        "date_debut": "2027-01-10",
        "date_fin": "2027-03-10",
        "ects": ects,
        "statut": statut,
    }


@pytest.mark.django_db
class TestStages:
    def test_le_secretariat_enregistre_un_stage(self, client, secretaire, etudiant):
        client.force_login(secretaire)
        client.post(reverse("administration:stage_create"), champs_stage(etudiant))
        assert Stage.objects.filter(etudiant=etudiant).exists()
        assert Notification.objects.filter(destinataire=etudiant.utilisateur, titre="Stage enregistré").exists()

    def test_un_stage_en_cours_ne_credite_rien(self, client, secretaire, etudiant):
        client.force_login(secretaire)
        client.post(reverse("administration:stage_create"), champs_stage(etudiant))
        assert not CreditECTS.objects.filter(etudiant=etudiant).exists()

    def test_valider_un_stage_porte_les_ects_au_dossier(self, client, secretaire, etudiant):
        client.force_login(secretaire)
        client.post(reverse("administration:stage_create"), champs_stage(etudiant, Stage.StatutStage.VALIDE))

        credit = CreditECTS.objects.get(etudiant=etudiant)
        assert float(credit.ects_obtenus) == 30
        assert credit.stage is not None
        etudiant.refresh_from_db()
        assert float(etudiant.total_ects_acquis) == 30

    def test_revenir_sur_la_validation_retire_les_ects(self, client, secretaire, etudiant):
        """Une décision reprise doit rendre le dossier conforme, pas le laisser crédité à tort."""
        client.force_login(secretaire)
        client.post(reverse("administration:stage_create"), champs_stage(etudiant, Stage.StatutStage.VALIDE))
        stage = Stage.objects.get(etudiant=etudiant)
        assert CreditECTS.objects.filter(stage=stage).exists()

        client.post(
            reverse("administration:stage_update", kwargs={"pk": stage.pk}),
            champs_stage(etudiant, Stage.StatutStage.NON_VALIDE),
        )
        assert not CreditECTS.objects.filter(stage=stage).exists()

    def test_enregistrer_deux_fois_ne_credite_pas_deux_fois(self, client, secretaire, etudiant):
        client.force_login(secretaire)
        client.post(reverse("administration:stage_create"), champs_stage(etudiant, Stage.StatutStage.VALIDE))
        stage = Stage.objects.get(etudiant=etudiant)
        client.post(
            reverse("administration:stage_update", kwargs={"pk": stage.pk}),
            champs_stage(etudiant, Stage.StatutStage.VALIDE),
        )
        assert CreditECTS.objects.filter(etudiant=etudiant).count() == 1

    def test_une_fin_anterieure_au_debut_est_refusee(self, client, secretaire, etudiant):
        client.force_login(secretaire)
        donnees = champs_stage(etudiant) | {"date_debut": "2027-03-10", "date_fin": "2027-01-10"}
        reponse = client.post(reverse("administration:stage_create"), donnees)
        assert reponse.status_code == 200
        assert not Stage.objects.filter(etudiant=etudiant).exists()

    def test_un_etudiant_est_refuse(self, client, etudiant):
        client.force_login(etudiant.utilisateur)
        assert client.get(reverse("administration:stages")).status_code in (302, 403)


@pytest.mark.django_db
class TestValidationDesAcquis:
    def test_la_vae_est_ouverte_au_secretariat(self, client, secretaire):
        """La maîtrise d'ouvrage a ouvert la VAE : le secrétariat instruit les dossiers."""
        client.force_login(secretaire)
        assert client.get(reverse("administration:vae")).status_code == 200

    def test_l_administration_ouvre_un_dossier(self, client, admin, etudiant):
        client.force_login(admin)
        client.post(
            reverse("administration:vae_create"),
            {
                "etudiant": etudiant.pk,
                "description_experience": "Quinze ans de responsabilité pastorale.",
                "ects_demandes": "30",
                "ects_accordes": "0",
                "statut": VAE.StatutVAE.SOUMIS,
            },
        )
        assert VAE.objects.filter(etudiant=etudiant).exists()
        assert not CreditECTS.objects.filter(etudiant=etudiant).exists()
        assert Notification.objects.filter(
            destinataire=etudiant.utilisateur,
            titre="Dossier VAE enregistré",
        ).exists()

    def test_accorder_porte_les_ects_accordes_et_non_les_demandes(self, client, admin, etudiant):
        client.force_login(admin)
        client.post(
            reverse("administration:vae_create"),
            {
                "etudiant": etudiant.pk,
                "description_experience": "Quinze ans de responsabilité pastorale.",
                "ects_demandes": "30",
                "ects_accordes": "18",
                "statut": VAE.StatutVAE.ACCORDE,
                "date_decision": "2027-05-12",
            },
        )
        credit = CreditECTS.objects.get(etudiant=etudiant)
        assert float(credit.ects_obtenus) == 18
        assert credit.vae is not None

    def test_on_n_accorde_pas_plus_que_demande(self, client, admin, etudiant):
        client.force_login(admin)
        reponse = client.post(
            reverse("administration:vae_create"),
            {
                "etudiant": etudiant.pk,
                "description_experience": "Expérience.",
                "ects_demandes": "10",
                "ects_accordes": "40",
                "statut": VAE.StatutVAE.EN_EXAMEN,
            },
        )
        assert reponse.status_code == 200
        assert not VAE.objects.filter(etudiant=etudiant).exists()

    def test_une_vae_accordee_doit_etre_datee(self, client, admin, etudiant):
        client.force_login(admin)
        reponse = client.post(
            reverse("administration:vae_create"),
            {
                "etudiant": etudiant.pk,
                "description_experience": "Expérience.",
                "ects_demandes": "10",
                "ects_accordes": "10",
                "statut": VAE.StatutVAE.ACCORDE,
            },
        )
        assert reponse.status_code == 200
        assert not VAE.objects.filter(etudiant=etudiant).exists()

    def test_refuser_apres_avoir_accorde_retire_les_ects(self, client, admin, etudiant):
        client.force_login(admin)
        base = {
            "etudiant": etudiant.pk,
            "description_experience": "Expérience.",
            "ects_demandes": "20",
            "ects_accordes": "20",
            "date_decision": "2027-05-12",
        }
        client.post(reverse("administration:vae_create"), base | {"statut": VAE.StatutVAE.ACCORDE})
        dossier = VAE.objects.get(etudiant=etudiant)
        assert CreditECTS.objects.filter(vae=dossier).exists()

        client.post(
            reverse("administration:vae_update", kwargs={"pk": dossier.pk}),
            base | {"statut": VAE.StatutVAE.REFUSE, "ects_accordes": "0"},
        )
        assert not CreditECTS.objects.filter(vae=dossier).exists()

    def test_la_decision_est_journalisee(self, client, admin, etudiant):
        """Une VAE modifie un dossier académique : la trace n'est pas optionnelle."""
        from apps.core.models import JournalAudit

        dossier = VAE.objects.create(
            etudiant=etudiant, description_experience="Expérience.", ects_demandes="20", ects_accordes="0"
        )
        client.force_login(admin)
        client.post(
            reverse("administration:vae_update", kwargs={"pk": dossier.pk}),
            {
                "etudiant": etudiant.pk,
                "description_experience": "Expérience.",
                "ects_demandes": "20",
                "ects_accordes": "20",
                "statut": VAE.StatutVAE.ACCORDE,
                "date_decision": "2027-05-12",
            },
        )
        assert JournalAudit.objects.filter(action="modification").exists()
