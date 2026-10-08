"""Tests de la double authentification des comptes administratifs."""

import base64
import hmac
import re
import time
from urllib.parse import parse_qs, urlparse

import pytest
from django.contrib.auth.models import Permission
from django.core.management import call_command
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from django_otp import DEVICE_ID_SESSION_KEY
from django_otp.plugins.otp_static.models import StaticDevice
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.accounts.models import User
from apps.accounts.otp import appareil_confirme, deux_facteurs_requis, reinitialiser_second_facteur


def code_valide(appareil: TOTPDevice) -> str:
    """Simule le téléphone à partir du QR, indépendamment de django-otp."""
    parametres = parse_qs(urlparse(appareil.config_url).query)
    secret = parametres["secret"][0]
    cle = base64.b32decode(secret + "=" * (-len(secret) % 8))
    periode = int(parametres["period"][0])
    chiffres = int(parametres["digits"][0])
    assert parametres["algorithm"] == ["SHA1"]
    compteur = int(time.time()) // periode
    empreinte = hmac.digest(cle, compteur.to_bytes(8, "big"), "sha1")
    decalage = empreinte[-1] & 0x0F
    valeur = int.from_bytes(empreinte[decalage : decalage + 4], "big") & 0x7FFFFFFF
    return str(valeur % 10**chiffres).zfill(chiffres)


def motif_du_champ_code(reponse) -> str:
    """Lit la contrainte du formulaire réellement présenté dans le navigateur."""
    champ = re.search(r'<input\b[^>]*\bname="code"[^>]*>', reponse.content.decode())
    assert champ is not None
    motif = re.search(r'\bpattern="([^"]+)"', champ[0])
    assert motif is not None
    return motif[1]


def donnees_activation(page, code, **donnees):
    """Soumet le code avec le QR lié au formulaire affiché dans cet onglet."""
    return {"code": code, "appareil": page.context["appareil_enrolement"], **donnees}


def session_verifiee(client, utilisateur, appareil):
    """Prépare une session OTP existante sans consommer deux fois le même code."""
    client.force_login(utilisateur)
    session = client.session
    session[DEVICE_ID_SESSION_KEY] = appareil.persistent_id
    session.save()


@pytest.fixture(autouse=True)
def _second_facteur_actif(settings, monkeypatch):
    """Exige le second facteur et évite les changements de fenêtre pendant un test."""
    settings.OTP_ENFORCE = True
    monkeypatch.setattr(time, "time", lambda: 1_800_000_015.0)


@pytest.fixture
def secretaire(db):
    return User.objects.create_user(
        username="secretariat",
        email="secretariat@example.org",
        password="motdepasse-long-12",
        role=User.Role.SECRETARIAT,
    )


@pytest.fixture
def etudiant(db):
    return User.objects.create_user(
        username="etudiant2fa",
        email="etudiant2fa@example.org",
        password="motdepasse-long-12",
        role=User.Role.ETUDIANT,
    )


@pytest.mark.django_db
class TestRegleDuSecondFacteur:
    @pytest.mark.parametrize("derive", [0, 5])
    def test_le_generateur_suit_le_qr_et_le_vecteur_rfc_6238(self, secretaire, monkeypatch, derive):
        """Une application ne reçoit pas la dérive enregistrée sur le serveur."""
        monkeypatch.setattr(time, "time", lambda: 59)
        appareil = TOTPDevice(
            user=secretaire,
            key="3132333435363738393031323334353637383930",
            digits=8,
            drift=derive,
        )
        assert code_valide(appareil) == "94287082"

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

    def test_l_appareil_confirme_le_plus_recent_est_utilise(self, secretaire):
        ancien = TOTPDevice.objects.create(user=secretaire, name="Ancien", confirmed=True)
        recent = TOTPDevice.objects.create(user=secretaire, name="Nouveau", confirmed=True)
        TOTPDevice.objects.create(user=secretaire, name="En attente", confirmed=False)

        assert appareil_confirme(secretaire) == recent
        assert appareil_confirme(secretaire) != ancien


@pytest.mark.django_db
def test_commande_reinitialiser_2fa_supprime_appareils_sans_toucher_mot_de_passe(secretaire):
    TOTPDevice.objects.create(user=secretaire, name="ITEAG", confirmed=True)
    ancien_hash = secretaire.password

    call_command("reinitialiser_2fa", secretaire.email)

    assert not TOTPDevice.objects.filter(user=secretaire).exists()
    secretaire.refresh_from_db()
    assert secretaire.password == ancien_hash


@pytest.mark.django_db
class TestApplicationParLeMiddleware:
    def test_un_compte_sans_appareil_est_dirige_vers_l_activation(self, client, secretaire):
        client.force_login(secretaire)
        reponse = client.get(reverse("secretariat:dashboard"))
        assert reponse.status_code == 302
        assert reverse("accounts:otp_activation") in reponse.url

    def test_un_compte_enrole_mais_non_verifie_est_dirige_vers_la_verification(self, client, secretaire):
        TOTPDevice.objects.create(user=secretaire, name="ITEAG", confirmed=True)
        client.force_login(secretaire)
        reponse = client.get(reverse("secretariat:dashboard"))
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

    def test_decocher_la_confirmation_revoque_une_session_otp_existante(self, client, secretaire):
        appareil = TOTPDevice.objects.create(user=secretaire, name="ITEAG", confirmed=True)
        client.force_login(secretaire)
        verification = client.post(reverse("accounts:otp_verification"), {"code": code_valide(appareil)})
        assert verification.status_code == 302
        assert client.get(reverse("secretariat:dashboard")).status_code == 200
        TOTPDevice.objects.filter(pk=appareil.pk).update(confirmed=False)

        reponse = client.get(reverse("secretariat:dashboard"))

        assert reponse.status_code == 302
        assert reverse("accounts:otp_activation") in reponse.url
        client.get(reponse.url)
        nouveau = TOTPDevice.objects.get(user=secretaire, confirmed=False)
        assert nouveau.pk != appareil.pk
        assert nouveau.last_t == -1
        assert not TOTPDevice.objects.filter(pk=appareil.pk).exists()


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

    @pytest.mark.parametrize("chiffres", [6, 8])
    @pytest.mark.parametrize("separateur", ["", " ", "\u00a0", "\u202f"], ids=["sans", "ascii", "nbsp", "nnbsp"])
    def test_un_code_correct_confirme_l_appareil(self, client, secretaire, chiffres, separateur):
        client.force_login(secretaire)
        appareil = TOTPDevice.objects.create(user=secretaire, name="ITEAG", confirmed=False, digits=chiffres)
        page = client.get(reverse("accounts:otp_activation"))
        code = code_valide(appareil)
        code = separateur.join([code[: chiffres // 2], code[chiffres // 2 :]])
        assert f"Code à {chiffres} chiffres" in page.content.decode()
        assert re.fullmatch(motif_du_champ_code(page), code) is not None

        reponse = client.post(
            reverse("accounts:otp_activation"),
            donnees_activation(page, code, suivant="/espace-admin/"),
        )
        assert reponse.status_code == 302
        assert reponse.url == "/espace-admin/"
        assert appareil_confirme(secretaire) is not None

    def test_un_code_faux_ne_confirme_rien(self, client, secretaire):
        client.force_login(secretaire)
        page = client.get(reverse("accounts:otp_activation"))
        reponse = client.post(reverse("accounts:otp_activation"), donnees_activation(page, "000000"))
        assert reponse.status_code == 200
        assert appareil_confirme(secretaire) is None

    def test_recharger_le_qr_ne_reinitialise_pas_le_blocage_des_tentatives(self, client, secretaire):
        appareil = TOTPDevice.objects.create(
            user=secretaire,
            name="ITEAG",
            confirmed=False,
            throttling_failure_count=8,
            throttling_failure_timestamp=timezone.now(),
        )
        client.force_login(secretaire)
        page = client.get(reverse("accounts:otp_activation"))

        reponse = client.post(reverse("accounts:otp_activation"), donnees_activation(page, code_valide(appareil)))

        assert reponse.status_code == 200
        assert "Trop de tentatives rapprochées" in reponse.content.decode()
        appareil.refresh_from_db()
        assert appareil.confirmed is False
        assert appareil.throttling_failure_count == 8
        assert appareil.last_t == -1
        assert DEVICE_ID_SESSION_KEY not in client.session

    def test_apres_activation_l_espace_est_accessible(self, client, secretaire):
        client.force_login(secretaire)
        page = client.get(reverse("accounts:otp_activation"))
        appareil = TOTPDevice.objects.get(user=secretaire, confirmed=False)
        client.post(reverse("accounts:otp_activation"), donnees_activation(page, code_valide(appareil)))
        assert client.get(reverse("secretariat:dashboard")).status_code == 200

    def test_un_post_sans_qr_affiche_demande_d_abord_de_scanner(self, client, secretaire):
        client.force_login(secretaire)
        appareil = TOTPDevice.objects.create(user=secretaire, name="ITEAG", confirmed=False)

        reponse = client.post(reverse("accounts:otp_activation"), {"code": code_valide(appareil)})

        assert reponse.status_code == 200
        assert "Scannez" in reponse.content.decode()
        assert "data:image/png;base64," in reponse.content.decode()
        assert appareil_confirme(secretaire) is None
        assert DEVICE_ID_SESSION_KEY not in client.session

        appareil = TOTPDevice.objects.get(user=secretaire, confirmed=False)
        seconde = client.post(reverse("accounts:otp_activation"), donnees_activation(reponse, code_valide(appareil)))
        assert seconde.status_code == 302
        assert client.get(reverse("secretariat:dashboard")).status_code == 200

    @pytest.mark.parametrize("changement", ["suppression", "remplacement", "cle"])
    def test_un_qr_devenu_obsolete_ne_confirme_pas_un_autre_secret(self, client, secretaire, changement):
        client.force_login(secretaire)
        page = client.get(reverse("accounts:otp_activation"))
        appareil = TOTPDevice.objects.get(user=secretaire, confirmed=False)
        ancien_code = code_valide(appareil)

        if changement == "cle":
            appareil.key = TOTPDevice().key
            appareil.save(update_fields=["key"])
        else:
            appareil.delete()
            if changement == "remplacement":
                TOTPDevice.objects.create(user=secretaire, name="Remplacement", confirmed=False)

        reponse = client.post(reverse("accounts:otp_activation"), donnees_activation(page, ancien_code))

        assert reponse.status_code == 200
        assert "Scannez" in reponse.content.decode()
        assert "data:image/png;base64," in reponse.content.decode()
        assert appareil_confirme(secretaire) is None
        assert DEVICE_ID_SESSION_KEY not in client.session
        nouveau = TOTPDevice.objects.get(user=secretaire, confirmed=False)
        assert nouveau.last_t == -1
        assert nouveau.throttling_failure_count == 0

        seconde = client.post(reverse("accounts:otp_activation"), donnees_activation(reponse, code_valide(nouveau)))
        assert seconde.status_code == 302

    def test_un_ancien_onglet_ne_peut_pas_confirmer_le_qr_d_un_nouvel_onglet(self, client, secretaire):
        client.force_login(secretaire)
        ancienne_page = client.get(reverse("accounts:otp_activation"))
        reinitialiser_second_facteur(secretaire)
        nouvelle_page = client.get(reverse("accounts:otp_activation"))
        nouveau = TOTPDevice.objects.get(user=secretaire, confirmed=False)
        nouveau_code = code_valide(nouveau)

        # Même si le code coïncide, le formulaire de l'ancien QR reste obsolète.
        reponse = client.post(reverse("accounts:otp_activation"), donnees_activation(ancienne_page, nouveau_code))

        assert reponse.status_code == 200
        assert "Scannez" in reponse.content.decode()
        assert appareil_confirme(secretaire) is None
        nouveau.refresh_from_db()
        assert nouveau.last_t == -1
        assert nouveau.throttling_failure_count == 0

        seconde = client.post(reverse("accounts:otp_activation"), donnees_activation(nouvelle_page, nouveau_code))
        assert seconde.status_code == 302

    @pytest.mark.parametrize("etat", ["derive", "utilise", "derniere_utilisation", "origine"])
    def test_un_appareil_non_confirme_herite_est_remplace(self, client, secretaire, etat):
        valeurs = {
            "derive": {"drift": 5},
            "utilise": {"last_t": 0},
            "derniere_utilisation": {"last_used_at": timezone.now()},
            "origine": {"t0": 60},
        }[etat]
        ancien = TOTPDevice.objects.create(user=secretaire, name="Ancien", confirmed=False, **valeurs)
        ancienne_cle = ancien.key
        client.force_login(secretaire)

        page = client.get(reverse("accounts:otp_activation"))

        assert page.status_code == 200
        nouveau = TOTPDevice.objects.get(user=secretaire, confirmed=False)
        assert nouveau.pk != ancien.pk
        assert nouveau.key != ancienne_cle
        assert not TOTPDevice.objects.filter(pk=ancien.pk).exists()
        assert nouveau.drift == 0
        assert nouveau.last_t == -1
        assert nouveau.t0 == 0
        assert nouveau.last_used_at is None
        assert nouveau.throttling_failure_count == 0

        reponse = client.post(reverse("accounts:otp_activation"), donnees_activation(page, code_valide(nouveau)))
        assert reponse.status_code == 302


@pytest.mark.django_db
class TestVerification:
    @pytest.mark.parametrize("chiffres", [6, 8])
    @pytest.mark.parametrize("separateur", ["", " ", "\u00a0", "\u202f"], ids=["sans", "ascii", "nbsp", "nnbsp"])
    def test_un_code_correct_ouvre_la_session(self, client, secretaire, chiffres, separateur):
        appareil = TOTPDevice.objects.create(user=secretaire, name="ITEAG", confirmed=True, digits=chiffres)
        client.force_login(secretaire)
        page = client.get(reverse("accounts:otp_verification"))
        code = code_valide(appareil)
        code = separateur.join([code[: chiffres // 2], code[chiffres // 2 :]])
        assert f"Code à {chiffres} chiffres" in page.content.decode()
        assert re.fullmatch(motif_du_champ_code(page), code) is not None

        reponse = client.post(
            reverse("accounts:otp_verification"),
            {"code": code, "suivant": reverse("secretariat:dashboard")},
        )
        assert reponse.status_code == 302
        assert client.get(reverse("secretariat:dashboard")).status_code == 200

    def test_un_code_valide_sur_un_autre_appareil_confirme_est_accepte(self, client, secretaire):
        appareil_valide = TOTPDevice.objects.create(user=secretaire, name="Téléphone actuel", confirmed=True)
        TOTPDevice.objects.create(user=secretaire, name="Ancien appareil", confirmed=True)
        client.force_login(secretaire)

        reponse = client.post(
            reverse("accounts:otp_verification"),
            {"code": code_valide(appareil_valide)},
        )

        assert reponse.status_code == 302

    @pytest.mark.parametrize("chiffres_ancien,chiffres_recent", [(6, 8), (8, 6)])
    def test_le_formulaire_accepte_le_code_d_un_autre_appareil_de_longueur_differente(
        self, client, secretaire, chiffres_ancien, chiffres_recent
    ):
        ancien = TOTPDevice.objects.create(
            user=secretaire, name="Téléphone actuel", confirmed=True, digits=chiffres_ancien
        )
        TOTPDevice.objects.create(user=secretaire, name="Autre téléphone", confirmed=True, digits=chiffres_recent)
        client.force_login(secretaire)
        page = client.get(reverse("accounts:otp_verification"))
        code = code_valide(ancien)
        code = f"{code[:3]}\u00a0{code[3:]}"

        assert "Code à 6 ou 8 chiffres" in page.content.decode()
        assert re.fullmatch(motif_du_champ_code(page), code) is not None

        reponse = client.post(reverse("accounts:otp_verification"), {"code": code})

        assert reponse.status_code == 302
        assert client.session[DEVICE_ID_SESSION_KEY] == ancien.persistent_id

    def test_un_appareil_obsolete_bloque_n_empeche_pas_le_bon_code(self, client, secretaire):
        appareil_valide = TOTPDevice.objects.create(user=secretaire, name="Téléphone actuel", confirmed=True)
        TOTPDevice.objects.create(
            user=secretaire,
            name="Ancien appareil",
            confirmed=True,
            throttling_failure_count=4,
            throttling_failure_timestamp=timezone.now(),
        )
        client.force_login(secretaire)

        reponse = client.post(
            reverse("accounts:otp_verification"),
            {"code": code_valide(appareil_valide)},
        )

        assert reponse.status_code == 302

    def test_un_code_faux_est_refuse_et_journalise(self, client, secretaire):
        from apps.core.models import JournalAudit

        TOTPDevice.objects.create(user=secretaire, name="ITEAG", confirmed=True)
        client.force_login(secretaire)
        reponse = client.post(reverse("accounts:otp_verification"), {"code": "000000"})
        assert reponse.status_code == 200
        assert JournalAudit.objects.filter(action="connexion_echec", objet_libelle="Second facteur invalide").exists()

    def test_autre_compte_deconnecte_et_revient_a_la_connexion(self, client, secretaire):
        """Le lien de l'écran OTP doit utiliser le POST exigé par Django."""
        TOTPDevice.objects.create(user=secretaire, name="ITEAG", confirmed=True)
        client.force_login(secretaire)

        page = client.get(reverse("accounts:otp_verification"))
        contenu = page.content.decode()
        assert f'action="{reverse("accounts:logout")}"' in contenu
        assert 'method="post"' in contenu
        assert f'name="next" value="{reverse("accounts:login")}"' in contenu

        reponse = client.post(
            reverse("accounts:logout"),
            {"next": reverse("accounts:login")},
        )
        assert reponse.status_code == 302
        assert reponse.url == reverse("accounts:login")

        connexion = client.get(reverse("accounts:login"))
        assert connexion.status_code == 200
        assert "_auth_user_id" not in client.session

    def test_un_code_deja_utilise_est_identifie_comme_tel(self, client, secretaire):
        appareil = TOTPDevice.objects.create(user=secretaire, name="ITEAG", confirmed=True)
        client.force_login(secretaire)
        code = code_valide(appareil)

        premiere = client.post(reverse("accounts:otp_verification"), {"code": code})
        assert premiere.status_code == 302

        client.post(reverse("accounts:logout"))
        client.force_login(secretaire)
        seconde = client.post(reverse("accounts:otp_verification"), {"code": code})

        assert seconde.status_code == 200
        assert "déjà été utilisé" in seconde.content.decode()

    @pytest.mark.parametrize("avance", [1, 10])
    def test_un_compteur_anti_rejeu_futur_est_conserve_et_le_code_est_refuse(self, client, secretaire, avance):
        compteur_futur = int(time.time()) // 30 + avance
        appareil = TOTPDevice.objects.create(user=secretaire, name="ITEAG", confirmed=True, last_t=compteur_futur)
        client.force_login(secretaire)

        reponse = client.post(reverse("accounts:otp_verification"), {"code": code_valide(appareil)})

        assert reponse.status_code == 200
        appareil.refresh_from_db()
        assert appareil.last_t == compteur_futur
        assert appareil.throttling_failure_count == 1
        assert DEVICE_ID_SESSION_KEY not in client.session

    def test_le_throttling_n_est_pas_affiche_comme_un_mauvais_code(self, client, secretaire):
        appareil = TOTPDevice.objects.create(
            user=secretaire,
            name="ITEAG",
            confirmed=True,
            throttling_failure_count=3,
            throttling_failure_timestamp=timezone.now(),
        )
        client.force_login(secretaire)

        reponse = client.post(
            reverse("accounts:otp_verification"),
            {"code": code_valide(appareil)},
        )

        assert reponse.status_code == 200
        assert "Trop de tentatives rapprochées" in reponse.content.decode()
        appareil.refresh_from_db()
        assert appareil.throttling_failure_count == 3

    def test_une_redirection_externe_est_refusee(self, client, secretaire):
        """La page ne doit pas servir de tremplin vers un site tiers."""
        appareil = TOTPDevice.objects.create(user=secretaire, name="ITEAG", confirmed=True)
        client.force_login(secretaire)
        reponse = client.post(
            reverse("accounts:otp_verification"),
            {"code": code_valide(appareil), "suivant": "//exemple-malveillant.org/"},
        )
        assert reponse.url == reverse("secretariat:dashboard")


@pytest.mark.django_db
class TestReinitialisation:
    def test_tous_les_appareils_du_compte_et_ses_sessions_otp_sont_invalides(self, client, secretaire, etudiant):
        premier = TOTPDevice.objects.create(user=secretaire, name="Téléphone", confirmed=True)
        second = TOTPDevice.objects.create(user=secretaire, name="Autre téléphone", confirmed=True)
        TOTPDevice.objects.create(user=secretaire, name="En attente", confirmed=False)
        autre_compte = TOTPDevice.objects.create(user=etudiant, name="Personnel", confirmed=True)
        secours = StaticDevice.objects.create(user=secretaire, name="Codes de secours", confirmed=True)
        autre_secours = StaticDevice.objects.create(user=etudiant, name="Secours personnel", confirmed=True)
        autre_client = Client()
        client_secours = Client()
        session_verifiee(client, secretaire, premier)
        session_verifiee(autre_client, secretaire, second)
        session_verifiee(client_secours, secretaire, secours)
        for session_client in (client, autre_client, client_secours):
            assert session_client.get(reverse("secretariat:dashboard")).status_code == 200

        nb_totp, nb_static = reinitialiser_second_facteur(secretaire)

        assert nb_totp == 3
        assert nb_static == 1
        assert not TOTPDevice.objects.filter(user=secretaire).exists()
        assert not StaticDevice.objects.filter(user=secretaire).exists()
        assert TOTPDevice.objects.filter(pk=autre_compte.pk).exists()
        assert StaticDevice.objects.filter(pk=autre_secours.pk).exists()
        for session_client in (client, autre_client, client_secours):
            reponse = session_client.get(reverse("secretariat:dashboard"))
            assert reponse.status_code == 302
            assert reverse("accounts:otp_activation") in reponse.url
            assert DEVICE_ID_SESSION_KEY not in session_client.session

    def test_le_nouveau_qr_utilise_une_cle_et_un_etat_neufs(self, client, secretaire):
        ancien = TOTPDevice.objects.create(
            user=secretaire,
            name="Ancien",
            confirmed=True,
            step=45,
            digits=8,
            drift=5,
            last_t=int(time.time()) // 30 + 10,
            last_used_at=timezone.now(),
            throttling_failure_count=8,
            throttling_failure_timestamp=timezone.now(),
        )
        client.force_login(secretaire)

        reinitialiser_second_facteur(secretaire)
        page = client.get(reverse("accounts:otp_activation"))

        assert page.status_code == 200
        assert "data:image/png;base64," in page.content.decode()
        nouveau = TOTPDevice.objects.get(user=secretaire, confirmed=False)
        assert nouveau.pk != ancien.pk
        assert nouveau.key != ancien.key
        assert nouveau.step == 30
        assert nouveau.digits == 6
        assert nouveau.t0 == 0
        assert nouveau.drift == 0
        assert nouveau.last_t == -1
        assert nouveau.last_used_at is None
        assert nouveau.throttling_failure_count == 0
        assert nouveau.throttling_failure_timestamp is None

        reponse = client.post(reverse("accounts:otp_activation"), donnees_activation(page, code_valide(nouveau)))
        assert reponse.status_code == 302
        assert client.get(reverse("secretariat:dashboard")).status_code == 200

    def test_l_action_administrative_reinitialise_le_compte_et_journalise(self, client, admin_user, secretaire):
        from apps.core.models import JournalAudit

        appareil_admin = TOTPDevice.objects.create(user=admin_user, name="Administrateur", confirmed=True)
        session_verifiee(client, admin_user, appareil_admin)
        TOTPDevice.objects.create(user=secretaire, name="Téléphone", confirmed=True)
        TOTPDevice.objects.create(user=secretaire, name="En attente", confirmed=False)
        appareil_secours = StaticDevice.objects.create(user=secretaire, name="Codes de secours", confirmed=True)

        reponse = client.post(
            reverse("admin:accounts_user_changelist"),
            {"action": "reinitialiser_otp", "_selected_action": [str(secretaire.pk)], "index": "0"},
        )

        assert reponse.status_code == 302
        assert not TOTPDevice.objects.filter(user=secretaire).exists()
        assert not StaticDevice.objects.filter(pk=appareil_secours.pk).exists()
        assert TOTPDevice.objects.filter(pk=appareil_admin.pk).exists()
        assert JournalAudit.objects.filter(
            action="modification",
            objet_libelle="Réinitialisation du second facteur",
            objet_id=str(secretaire.pk),
            utilisateur=admin_user,
        ).exists()

    def test_un_administrateur_sans_permission_de_modification_ne_peut_pas_reinitialiser(self, client, secretaire):
        lecture_seule = User.objects.create_user(
            username="lecture-seule-otp",
            email="lecture-seule-otp@example.org",
            password="motdepasse-long-12",
            is_staff=True,
        )
        permission = Permission.objects.get(content_type__app_label="accounts", codename="view_user")
        lecture_seule.user_permissions.add(permission)
        appareil_lecture = TOTPDevice.objects.create(user=lecture_seule, name="Lecture seule", confirmed=True)
        appareil_cible = TOTPDevice.objects.create(user=secretaire, name="Téléphone", confirmed=True)
        session_verifiee(client, lecture_seule, appareil_lecture)

        reponse = client.post(
            reverse("admin:accounts_user_changelist"),
            {"action": "reinitialiser_otp", "_selected_action": [str(secretaire.pk)], "index": "0"},
        )

        assert reponse.status_code in (200, 302, 403)
        assert TOTPDevice.objects.filter(pk=appareil_cible.pk).exists()
