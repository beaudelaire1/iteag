"""Ouverture des comptes nominatifs du personnel."""

import importlib
import re

import pytest
from django.core import mail
from django.urls import reverse

from apps.accounts.models import User
from apps.administration.services.personnel import (
    MOT_DE_PASSE_DEMONSTRATION,
    PERSONNEL_ITEAG,
    installer_personnel_iteag,
)
from apps.formations.models import Professeur

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _boites_reelles(settings):
    settings.SITE_URL = "https://iteag.org"
    settings.ITEAG_COURRIEL_SECRETARIAT = "secretariat.iteag@gmail.com"
    settings.ITEAG_COURRIEL_COPIE = "contact.iteag@gmail.com"


def _lien(message) -> str:
    return re.search(r"https://iteag\.org(/mot-de-passe/confirmer/[^\"\s<]+/)", message.alternatives[0].content)[1]


class TestOuverture:
    def test_chacun_recoit_le_role_de_son_espace(self):
        installer_personnel_iteag()

        identifiants = [membre.identifiant for membre in PERSONNEL_ITEAG]
        roles = dict(User.objects.filter(username__in=identifiants).values_list("username", "role"))
        assert roles == {
            "viviane.foucan": User.Role.SECRETARIAT,
            "alain.nisus": User.Role.ENSEIGNANT,
            "patricia.alphonse": User.Role.ADMIN,
        }

    def test_la_secretaire_utilise_la_boite_du_secretariat(self):
        installer_personnel_iteag()

        assert User.objects.get(username="viviane.foucan").email == "secretariat.iteag@gmail.com"

    def test_le_professeur_est_rattache_a_sa_fiche(self):
        fiche = Professeur.objects.create(nom="Nisus", prenom="Alain", slug="alain-nisus")

        installer_personnel_iteag()

        fiche.refresh_from_db()
        assert fiche.user.username == "alain.nisus"

    def test_personne_ne_connait_le_mot_de_passe(self):
        installer_personnel_iteag()

        compte = User.objects.get(username="viviane.foucan")
        # Utilisable, pour que « Mot de passe oublié » reste un recours.
        assert compte.has_usable_password()
        assert not compte.check_password(MOT_DE_PASSE_DEMONSTRATION)


class TestInvitation:
    def test_une_invitation_par_adresse_connue_et_aucune_copie(self):
        bilan = installer_personnel_iteag()

        assert sorted(bilan["invites"]) == ["alain.nisus", "viviane.foucan"]
        assert sorted(m.to[0] for m in mail.outbox) == ["anisus971@gmail.com", "secretariat.iteag@gmail.com"]
        # Le lien ouvre le compte : il ne doit pas atterrir dans la boîte de contact.
        assert all(m.cc == [] for m in mail.outbox)

    def test_la_secretaire_est_prevenue_du_second_facteur(self, settings):
        settings.OTP_ENFORCE = True
        installer_personnel_iteag()

        html = next(m for m in mail.outbox if m.to == ["secretariat.iteag@gmail.com"]).alternatives[0].content
        assert "Google Authenticator" in html
        assert "l&#x27;espace secrétariat" in html or "l'espace secrétariat" in html

    def test_le_lien_permet_de_choisir_son_mot_de_passe_puis_mene_au_second_facteur(self, client, settings):
        settings.OTP_ENFORCE = True
        installer_personnel_iteag()
        message = next(m for m in mail.outbox if m.to == ["secretariat.iteag@gmail.com"])

        formulaire = client.get(_lien(message), follow=True)
        assert formulaire.status_code == 200
        reponse = client.post(
            formulaire.redirect_chain[-1][0],
            {"new_password1": "Un-vrai-secret-2026", "new_password2": "Un-vrai-secret-2026"},
        )
        assert reponse.status_code == 302

        compte = User.objects.get(username="viviane.foucan")
        assert compte.check_password("Un-vrai-secret-2026")
        client.force_login(compte)
        espace = client.get(reverse("secretariat:dashboard"))
        assert espace.status_code == 302
        assert espace.url.startswith(reverse("accounts:otp_activation"))

    def test_sans_adresse_le_compte_existe_sans_invitation(self):
        bilan = installer_personnel_iteag()

        assert "patricia.alphonse" in bilan["ouverts"]
        assert "patricia.alphonse" not in bilan["invites"]


class TestReprise:
    def test_un_second_passage_ne_reinvite_ni_ne_reecrit(self):
        installer_personnel_iteag()
        compte = User.objects.get(username="viviane.foucan")
        compte.set_password("Choisi-par-elle-2026")
        compte.phone = "0690000000"
        compte.save()
        mail.outbox.clear()

        installer_personnel_iteag()

        compte.refresh_from_db()
        assert compte.check_password("Choisi-par-elle-2026")
        assert compte.phone == "0690000000"
        assert [m.to for m in mail.outbox] == []

    def test_le_compte_de_demonstration_du_professeur_est_repris(self):
        ancien = User.objects.create_user(
            username="alain.nisus",
            email="alain.nisus@iteag.org",
            password=MOT_DE_PASSE_DEMONSTRATION,
            role=User.Role.ENSEIGNANT,
        )
        Professeur.objects.create(nom="Nisus", prenom="Alain", slug="alain-nisus", user=ancien)

        installer_personnel_iteag()

        ancien.refresh_from_db()
        assert ancien.email == "anisus971@gmail.com"
        assert not ancien.check_password(MOT_DE_PASSE_DEMONSTRATION)
        assert User.objects.filter(role=User.Role.ENSEIGNANT, last_name="Nisus").count() == 1

    def test_les_comptes_de_service_de_demonstration_sont_refermes(self):
        for identifiant, role in (("secretariat_iteag", User.Role.SECRETARIAT), ("direction_iteag", User.Role.ADMIN)):
            User.objects.create_user(username=identifiant, password=MOT_DE_PASSE_DEMONSTRATION, role=role)
        enseignant = User.objects.create_user(
            username="cedric.eugene", password=MOT_DE_PASSE_DEMONSTRATION, role=User.Role.ENSEIGNANT
        )
        etudiant = User.objects.create_user(username="etu", password=MOT_DE_PASSE_DEMONSTRATION)

        bilan = installer_personnel_iteag()

        assert sorted(bilan["neutralises"]) == ["cedric.eugene", "direction_iteag", "secretariat_iteag"]
        assert not User.objects.filter(username__in=["secretariat_iteag", "direction_iteag"], is_active=True).exists()
        enseignant.refresh_from_db()
        assert enseignant.is_active and not enseignant.check_password(MOT_DE_PASSE_DEMONSTRATION)
        etudiant.refresh_from_db()
        assert etudiant.check_password(MOT_DE_PASSE_DEMONSTRATION)


class TestMigration:
    migration = importlib.import_module("apps.accounts.migrations.0006_personnel_iteag")

    def test_sans_arborescence_wagtail_la_migration_ne_cree_rien(self):
        from django.apps import apps

        self.migration.ouvrir_les_comptes(apps, None)

        assert not User.objects.filter(username="viviane.foucan").exists()

    def test_sur_la_base_en_service_la_migration_ouvre_les_comptes(self):
        from django.apps import apps
        from wagtail.models import Page

        from apps.website.models import HomePage

        Page.get_first_root_node().add_child(instance=HomePage(title="Accueil", slug="accueil-personnel"))

        self.migration.ouvrir_les_comptes(apps, None)

        assert User.objects.filter(username="viviane.foucan", role=User.Role.SECRETARIAT).exists()
