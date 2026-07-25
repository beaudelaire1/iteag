"""Tests de la double authentification des comptes administratifs."""

import time

import pytest
from django.urls import reverse
from django_otp.oath import TOTP
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.accounts.models import User
from apps.accounts.otp import appareil_confirme, deux_facteurs_requis


def code_valide(appareil: TOTPDevice) -> str:
    """Code que produirait l'application d'authentification à cet instant."""
    totp = TOTP(appareil.bin_key, appareil.step, appareil.t0, appareil.digits, appareil.drift)
    totp.time = time.time()
    return str(totp.token()).zfill(appareil.digits)


@pytest.fixture(autouse=True)
def _second_facteur_actif(settings):
    """Ces tests portent sur le second facteur : il est donc exigé partout ici."""
    settings.OTP_ENFORCE = True


@pytest.fixture
def secretaire(db):
    return User.objects.create_user(
        username="secretariat",
        email="secretariat@iteag.org",
        password="motdepasse-long-12",
        role=User.Role.SECRETARIAT,
    )


@pytest.fixture
def etudiant(db):
    return User.objects.create_user(
        username="etudiant2fa",
        email="etudiant2fa@iteag.org",
        password="motdepasse-long-12",
        role=User.Role.ETUDIANT,
    )


@pytest.mark.django_db
class TestRegleDuSecondFacteur:
    def test_exige_pour_le_secretariat(self, secretaire):
        assert deux_facteurs_requis(secretaire) is True

    def test_exige_pour_un_superutilisateur(self, admin_user):
        assert deux_facteurs_requis(admin_user) is True

    def test_non_exige_pour_un_etudiant(self, etudiant):
        assert deux_facteurs_requis(etudiant) is False

    def test_non_exige_pour_un_anonyme(self):
        from django.contrib.auth.models import AnonymousUser

        assert deux_facteurs_requis(AnonymousUser()) is False

    def test_l_interrupteur_desactive_la_regle(self, secretaire, settings):
        settings.OTP_ENFORCE = False
        assert deux_facteurs_requis(secretaire) is False


@pytest.mark.django_db
class TestApplicationParLeMiddleware:
    def test_un_compte_sans_appareil_est_dirige_vers_l_activation(self, client, secretaire):
        client.force_login(secretaire)
        reponse = client.get(reverse("administration:dashboard"))
        assert reponse.status_code == 302
        assert reverse("accounts:otp_activation") in reponse.url

    def test_un_compte_enrole_mais_non_verifie_est_dirige_vers_la_verification(self, client, secretaire):
        TOTPDevice.objects.create(user=secretaire, name="ITEAG", confirmed=True)
        client.force_login(secretaire)
        reponse = client.get(reverse("administration:dashboard"))
        assert reponse.status_code == 302
        assert reverse("accounts:otp_verification") in reponse.url

    def test_un_etudiant_n_est_pas_intercepte(self, client, etudiant):
        client.force_login(etudiant)
        reponse = client.get(reverse("core:notifications"))
        assert reponse.status_code == 200

    def test_la_deconnexion_reste_accessible(self, client, secretaire):
        """Un compte bloqué par le second facteur doit pouvoir se déconnecter."""
        client.force_login(secretaire)
        # La déconnexion Django est en POST : un GET n'est pas une régression.
        assert client.post(reverse("accounts:logout")).status_code == 302

    def test_la_sonde_reste_accessible(self, client, secretaire):
        client.force_login(secretaire)
        assert client.get("/healthz").status_code == 200

    def test_la_page_d_activation_est_atteignable(self, client, secretaire):
        client.force_login(secretaire)
        assert client.get(reverse("accounts:otp_activation")).status_code == 200


@pytest.mark.django_db
class TestEnrolement:
    def test_la_page_fournit_un_qr_et_une_cle_manuelle(self, client, secretaire):
        client.force_login(secretaire)
        contenu = client.get(reverse("accounts:otp_activation")).content.decode()
        assert "data:image/png;base64," in contenu
        assert "saisissez cette clé manuellement" in contenu

    def test_le_secret_survit_a_un_rechargement(self, client, secretaire):
        client.force_login(secretaire)
        client.get(reverse("accounts:otp_activation"))
        premier = TOTPDevice.objects.get(user=secretaire, confirmed=False).key
        client.get(reverse("accounts:otp_activation"))
        assert TOTPDevice.objects.filter(user=secretaire, confirmed=False).count() == 1
        assert TOTPDevice.objects.get(user=secretaire, confirmed=False).key == premier

    def test_un_code_correct_confirme_l_appareil(self, client, secretaire):
        client.force_login(secretaire)
        client.get(reverse("accounts:otp_activation"))
        appareil = TOTPDevice.objects.get(user=secretaire, confirmed=False)

        reponse = client.post(
            reverse("accounts:otp_activation"),
            {"code": code_valide(appareil), "suivant": "/espace-admin/"},
        )
        assert reponse.status_code == 302
        assert reponse.url == "/espace-admin/"
        assert appareil_confirme(secretaire) is not None

    def test_un_code_faux_ne_confirme_rien(self, client, secretaire):
        client.force_login(secretaire)
        client.get(reverse("accounts:otp_activation"))
        reponse = client.post(reverse("accounts:otp_activation"), {"code": "000000"})
        assert reponse.status_code == 200
        assert appareil_confirme(secretaire) is None

    def test_apres_activation_l_espace_est_accessible(self, client, secretaire):
        client.force_login(secretaire)
        client.get(reverse("accounts:otp_activation"))
        appareil = TOTPDevice.objects.get(user=secretaire, confirmed=False)
        client.post(reverse("accounts:otp_activation"), {"code": code_valide(appareil)})
        assert client.get(reverse("administration:dashboard")).status_code == 200


@pytest.mark.django_db
class TestVerification:
    def test_un_code_correct_ouvre_la_session(self, client, secretaire):
        appareil = TOTPDevice.objects.create(user=secretaire, name="ITEAG", confirmed=True)
        client.force_login(secretaire)
        reponse = client.post(
            reverse("accounts:otp_verification"),
            {"code": code_valide(appareil), "suivant": "/espace-admin/"},
        )
        assert reponse.status_code == 302
        assert client.get(reverse("administration:dashboard")).status_code == 200

    def test_un_code_faux_est_refuse_et_journalise(self, client, secretaire):
        from apps.core.models import JournalAudit

        TOTPDevice.objects.create(user=secretaire, name="ITEAG", confirmed=True)
        client.force_login(secretaire)
        reponse = client.post(reverse("accounts:otp_verification"), {"code": "000000"})
        assert reponse.status_code == 200
        assert JournalAudit.objects.filter(action="connexion_echec", objet_libelle="Second facteur invalide").exists()

    def test_une_redirection_externe_est_refusee(self, client, secretaire):
        """La page ne doit pas servir de tremplin vers un site tiers."""
        appareil = TOTPDevice.objects.create(user=secretaire, name="ITEAG", confirmed=True)
        client.force_login(secretaire)
        reponse = client.post(
            reverse("accounts:otp_verification"),
            {"code": code_valide(appareil), "suivant": "//exemple-malveillant.org/"},
        )
        assert reponse.url == reverse("administration:dashboard")
