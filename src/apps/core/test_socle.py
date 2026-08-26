"""Tests du socle transverse — notifications, audit, newsletter, sonde."""

from io import StringIO
from unittest import mock

import pytest
from django.core import mail
from django.core.management import call_command
from django.core.management.base import CommandError
from django.template.loader import render_to_string
from django.test import override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.core.models import AbonneNewsletter, JournalAudit, Notification
from apps.core.services import notifications as service_notifications
from apps.core.services.audit import journaliser
from apps.core.services.emails import envoyer_email


@pytest.fixture
def etudiant(db):
    return User.objects.create_user(
        username="etu", email="etu@iteag.org", password="motdepasse-long-12", role=User.Role.ETUDIANT
    )


# ──────────────────────────────────────────────
# Notifications — ETU-009
# ──────────────────────────────────────────────


@pytest.mark.django_db
class TestServiceNotifications:
    def test_notifier_cree_la_notification(self, etudiant):
        notification = service_notifications.notifier(etudiant, "Nouvelle note", url_cible="/notes/")
        assert notification.pk is not None
        assert notification.destinataire == etudiant
        assert notification.lu is False

    def test_notifier_envoie_aussi_un_email_iteag(self, etudiant, django_capture_on_commit_callbacks):
        mail.outbox.clear()
        with django_capture_on_commit_callbacks(execute=True):
            service_notifications.notifier(
                etudiant,
                "Cours disponible",
                message="Un nouveau cours est ouvert.",
                url_cible="/espace-etudiant/catalogue/",
            )

        assert len(mail.outbox) == 1
        assert "Cours disponible" in mail.outbox[0].subject
        assert "Un nouveau cours est ouvert" in mail.outbox[0].body
        assert mail.outbox[0].alternatives

    def test_compte_inactif_n_est_pas_notifie(self, etudiant):
        etudiant.is_active = False
        etudiant.save(update_fields=["is_active"])
        assert service_notifications.notifier(etudiant, "Rien") is None

    def test_destinataire_absent_est_ignore(self):
        assert service_notifications.notifier(None, "Rien") is None

    def test_comptage_des_non_lues(self, etudiant):
        for i in range(3):
            service_notifications.notifier(etudiant, f"Message {i}")
        assert service_notifications.compter_non_lues(etudiant) == 3

    def test_marquer_lue_horodate(self, etudiant):
        notification = service_notifications.notifier(etudiant, "Message")
        notification.marquer_lue()
        notification.refresh_from_db()
        assert notification.lu is True
        assert notification.date_lecture is not None

    def test_marquer_tout_lu(self, etudiant):
        for i in range(4):
            service_notifications.notifier(etudiant, f"Message {i}")
        assert service_notifications.marquer_tout_lu(etudiant) == 4
        assert service_notifications.compter_non_lues(etudiant) == 0

    def test_notifications_d_un_autre_ne_sont_pas_comptees(self, etudiant, db):
        autre = User.objects.create_user(username="autre", email="a@iteag.org", password="motdepasse-long-12")
        service_notifications.notifier(autre, "Pour l'autre")
        assert service_notifications.compter_non_lues(etudiant) == 0


@pytest.mark.django_db
class TestVuesNotifications:
    def test_liste_exige_une_connexion(self, client):
        reponse = client.get(reverse("core:notifications"))
        assert reponse.status_code == 302

    def test_liste_affiche_les_siennes(self, client, etudiant):
        client.force_login(etudiant)
        service_notifications.notifier(etudiant, "Ma notification à moi")
        contenu = client.get(reverse("core:notifications")).content.decode()
        assert "Ma notification à moi" in contenu

    def test_on_ne_peut_pas_lire_la_notification_d_un_autre(self, client, etudiant, db):
        autre = User.objects.create_user(username="autre2", email="a2@iteag.org", password="motdepasse-long-12")
        notification = service_notifications.notifier(autre, "Confidentiel")
        client.force_login(etudiant)
        reponse = client.post(reverse("core:notification_lue", kwargs={"pk": notification.pk}))
        assert reponse.status_code == 404
        notification.refresh_from_db()
        assert notification.lu is False

    def test_consulter_redirige_vers_la_cible(self, client, etudiant):
        notification = service_notifications.notifier(etudiant, "Note", url_cible="/espace-etudiant/notes/")
        client.force_login(etudiant)
        reponse = client.post(reverse("core:notification_lue", kwargs={"pk": notification.pk}))
        assert reponse.status_code == 302
        assert reponse.url == "/espace-etudiant/notes/"


# ──────────────────────────────────────────────
# Journal d'audit — CDC §13
# ──────────────────────────────────────────────


@pytest.mark.django_db
class TestJournalAudit:
    def test_journalise_une_action_simple(self, etudiant):
        entree = journaliser("export", utilisateur=etudiant, objet_type="Etudiants", nombre=42)
        assert entree.action == "export"
        assert entree.metadonnees["nombre"] == 42

    def test_renseigne_l_objet_automatiquement(self, etudiant):
        entree = journaliser("modification", objet=etudiant)
        assert entree.objet_type == "User"
        assert entree.objet_id == str(etudiant.pk)
        assert entree.objet_libelle

    def test_retient_l_adresse_ip(self, request_factory, etudiant):
        requete = request_factory.get("/", REMOTE_ADDR="192.0.2.10", HTTP_USER_AGENT="Navigateur test")
        requete.user = etudiant
        entree = journaliser("connexion", request=requete)
        assert entree.adresse_ip == "192.0.2.10"
        assert entree.user_agent == "Navigateur test"
        assert entree.utilisateur == etudiant

    def test_prefere_l_adresse_transmise_par_le_proxy(self, request_factory, etudiant):
        requete = request_factory.get("/", HTTP_X_FORWARDED_FOR="203.0.113.5, 10.0.0.1", REMOTE_ADDR="10.0.0.1")
        requete.user = etudiant
        assert journaliser("connexion", request=requete).adresse_ip == "203.0.113.5"

    def test_survit_a_la_suppression_de_l_objet(self, etudiant):
        journaliser("suppression", objet=etudiant, objet_libelle="Compte supprimé")
        identifiant = etudiant.pk
        etudiant.delete()
        entree = JournalAudit.objects.get(objet_id=str(identifiant))
        assert entree.objet_libelle == "Compte supprimé"
        assert entree.utilisateur is None

    def test_le_journal_est_en_lecture_seule_dans_l_admin(self):
        from django.contrib import admin

        from apps.core.admin import JournalAuditAdmin

        registre = JournalAuditAdmin(JournalAudit, admin.site)
        assert registre.has_add_permission(None) is False
        assert registre.has_change_permission(None) is False
        assert registre.has_delete_permission(None) is False


@pytest.mark.django_db
class TestJournalisationConnexion:
    def test_une_connexion_reussie_est_tracee(self, client, etudiant):
        client.post(reverse("accounts:login"), {"username": "etu@iteag.org", "password": "motdepasse-long-12"})
        assert JournalAudit.objects.filter(action="connexion", utilisateur=etudiant).exists()

    def test_un_echec_est_trace(self, client, etudiant):
        client.post(reverse("accounts:login"), {"username": "etu@iteag.org", "password": "mauvais"})
        assert JournalAudit.objects.filter(action="connexion_echec").exists()


# ──────────────────────────────────────────────
# Newsletter — PUB-012
# ──────────────────────────────────────────────


@pytest.mark.django_db
class TestNewsletter:
    def test_inscription_envoie_un_email_de_confirmation(self, client):
        reponse = client.post(reverse("core:newsletter_inscription"), {"email": "lecteur@exemple.org"})
        assert reponse.status_code == 302
        abonne = AbonneNewsletter.objects.get(email="lecteur@exemple.org")
        assert abonne.confirme is False
        assert len(mail.outbox) == 1
        assert abonne.token_confirmation in mail.outbox[0].body

    def test_l_inscription_ne_vaut_rien_sans_confirmation(self, client):
        client.post(reverse("core:newsletter_inscription"), {"email": "lecteur@exemple.org"})
        assert AbonneNewsletter.objects.filter(confirme=True).count() == 0

    def test_confirmation_active_l_abonnement(self, client):
        client.post(reverse("core:newsletter_inscription"), {"email": "lecteur@exemple.org"})
        abonne = AbonneNewsletter.objects.get(email="lecteur@exemple.org")
        reponse = client.get(reverse("core:newsletter_confirmation", kwargs={"token": abonne.token_confirmation}))
        assert reponse.status_code == 200
        abonne.refresh_from_db()
        assert abonne.confirme is True
        assert abonne.date_confirmation is not None

    def test_desinscription(self, client):
        abonne = AbonneNewsletter.objects.create(email="lecteur@exemple.org")
        abonne.confirmer()
        client.get(reverse("core:newsletter_desinscription", kwargs={"token": abonne.token_desinscription}))
        abonne.refresh_from_db()
        assert abonne.actif is False
        assert abonne.date_desinscription is not None

    def test_un_jeton_inconnu_donne_404(self, client):
        reponse = client.get(reverse("core:newsletter_confirmation", kwargs={"token": "jeton-invente"}))
        assert reponse.status_code == 404

    def test_le_piege_a_robots_bloque_l_envoi(self, client):
        client.post(
            reverse("core:newsletter_inscription"),
            {"email": "robot@exemple.org", "site_web": "http://spam.example"},
        )
        assert AbonneNewsletter.objects.filter(email="robot@exemple.org").count() == 0
        assert len(mail.outbox) == 0

    def test_la_reponse_ne_revele_pas_l_appartenance_a_la_liste(self):
        """Un tiers ne doit pas pouvoir tester si une adresse est déjà inscrite."""
        from django.test import Client

        AbonneNewsletter.objects.create(email="deja@exemple.org").confirmer()

        # Deux clients distincts : les messages ne se cumulent pas d'une session à l'autre.
        inconnue = Client().post(reverse("core:newsletter_inscription"), {"email": "nouveau@exemple.org"}, follow=True)
        connue = Client().post(reverse("core:newsletter_inscription"), {"email": "deja@exemple.org"}, follow=True)

        assert [m.message for m in inconnue.context["messages"]] == [m.message for m in connue.context["messages"]]
        assert inconnue.status_code == connue.status_code

    def test_une_relance_invalide_l_ancien_lien(self, client):
        client.post(reverse("core:newsletter_inscription"), {"email": "lecteur@exemple.org"})
        ancien = AbonneNewsletter.objects.get(email="lecteur@exemple.org").token_confirmation
        client.post(reverse("core:newsletter_inscription"), {"email": "lecteur@exemple.org"})
        nouveau = AbonneNewsletter.objects.get(email="lecteur@exemple.org").token_confirmation
        assert ancien != nouveau
        assert client.get(reverse("core:newsletter_confirmation", kwargs={"token": ancien})).status_code == 404


# ──────────────────────────────────────────────
# Service d'envoi de courriels
# ──────────────────────────────────────────────


@pytest.mark.django_db
class TestServiceEmail:
    def test_envoi_avec_gabarit(self):
        envoye = envoyer_email(
            sujet="Test",
            gabarit="core/emails/newsletter_confirmation.html",
            contexte={"lien_confirmation": "https://exemple.org/x", "email": "a@b.org"},
            destinataires=["a@b.org"],
            differe=False,
        )
        assert envoye is True
        assert len(mail.outbox) == 1
        # « ITEAG - » et non « [ITEAG] » : des crochets dans un objet font
        # message de service, et certains filtres les pénalisent.
        assert mail.outbox[0].subject == "ITEAG - Test"
        assert mail.outbox[0].alternatives  # une version HTML accompagne le texte

    def test_email_integre_logo_et_identite_complete(self):
        assert envoyer_email(
            sujet="Identité ITEAG",
            gabarit="core/emails/notification.html",
            contexte={"titre": "Information", "message": "Message de contrôle."},
            destinataires=["a@b.org"],
            differe=False,
        )

        message = mail.outbox[0]
        html = message.alternatives[0].content
        assert 'src="cid:logo-iteag"' in html
        assert "Institut de Théologie Évangélique des Antilles et de la Guyane" in html
        assert "201 lot Pointe" in html
        assert "97139 Les Abymes" in html
        assert "+590 690 37 64 17" in html
        assert "secretariat@iteag.org" in html
        assert any(
            piece.get_content_type() == "image/png" and piece["Content-ID"] == "<logo-iteag>"
            for piece in message.attachments
        )

    def test_sans_destinataire_rien_n_est_envoye(self):
        assert envoyer_email(sujet="X", gabarit="x.html", contexte={}, destinataires=[], differe=False) is False
        assert len(mail.outbox) == 0

    def test_un_gabarit_absent_ne_leve_pas(self):
        assert (
            envoyer_email(
                sujet="X", gabarit="core/emails/inexistant.html", contexte={}, destinataires=["a@b.org"], differe=False
            )
            is False
        )

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_le_mode_local_envoie_sans_attendre_un_worker(self):
        with mock.patch("apps.core.services.emails.envoyer_maintenant", return_value=True) as envoi_immediat:
            assert (
                envoyer_email(
                    sujet="Test local",
                    gabarit="core/emails/newsletter_confirmation.html",
                    contexte={},
                    destinataires=["a@b.org"],
                )
                is True
            )

        envoi_immediat.assert_called_once()

    @override_settings(CELERY_TASK_ALWAYS_EAGER=False)
    def test_la_publication_ne_reessaie_pas_si_redis_est_absent(self):
        connexion = mock.MagicMock()
        connexion.__enter__.return_value = connexion
        with (
            mock.patch("apps.core.services.emails._connexion_celery", return_value=connexion),
            mock.patch("apps.core.tasks.envoyer_email_tache.apply_async") as publication,
        ):
            assert envoyer_email(
                sujet="Test différé",
                gabarit="core/emails/notification.html",
                contexte={"titre": "Test", "message": "Message"},
                destinataires=["a@b.org"],
            )

        publication.assert_called_once_with(
            args=[
                "Test différé",
                "core/emails/notification.html",
                {"titre": "Test", "message": "Message"},
                ["a@b.org"],
            ],
            connection=connexion,
            retry=False,
        )
        connexion.ensure_connection.assert_called_once_with(max_retries=0, timeout=0.5)

    @pytest.mark.parametrize(
        ("gabarit", "contexte", "texte_attendu"),
        [
            (
                "core/emails/notification.html",
                {
                    "titre": "Information importante",
                    "message": "Votre dossier a été mis à jour.",
                    "lien": "https://example.org/espace/",
                    "libelle_lien": "Ouvrir",
                },
                "Votre dossier a été mis à jour.",
            ),
            (
                "core/emails/newsletter_confirmation.html",
                {"email": "test@example.org", "lien_confirmation": "https://example.org/confirmer/"},
                "Confirmez votre inscription",
            ),
            (
                "administration/emails/bienvenue_etudiant.html",
                {
                    "prenom": "Test",
                    "parcours": "Parcours test",
                    "lien_activation": "https://example.org/activation/",
                },
                "Bienvenue, Test",
            ),
            (
                "accounts/password_reset_email.html",
                {
                    "protocol": "https",
                    "domain": "example.org",
                    "uid": "test",
                    "token": "test-token",
                },
                "Réinitialisation de votre mot de passe",
            ),
        ],
    )
    def test_chaque_gabarit_de_notification_contient_son_message(self, gabarit, contexte, texte_attendu):
        assert texte_attendu in render_to_string(gabarit, contexte)


class TestCommandeNotificationsEmail:
    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend",
        EMAIL_HOST="smtp.example.org",
        EMAIL_HOST_USER="test@example.org",
        EMAIL_HOST_PASSWORD="mot-de-passe-application",
        EMAIL_TEST_RECIPIENT="reception@example.org",
    )
    def test_envoie_les_quatre_notifications_de_controle(self):
        sortie = StringIO()
        with mock.patch(
            "apps.core.management.commands.tester_notifications_email.envoyer_maintenant",
            return_value=True,
        ) as envoi_html:
            call_command("tester_notifications_email", stdout=sortie)

        assert envoi_html.call_count == 4
        assert "4 notifications de contrôle envoyées" in sortie.getvalue()

    def test_refuse_un_faux_controle_sans_configuration_smtp(self):
        with pytest.raises(CommandError, match="SMTP"):
            call_command("tester_notifications_email", destinataire="reception@example.org")


# ──────────────────────────────────────────────
# Sonde de santé et pages d'erreur
# ──────────────────────────────────────────────


@pytest.mark.django_db
class TestSondeEtErreurs:
    def test_la_sonde_repond(self, client):
        reponse = client.get("/healthz")
        assert reponse.status_code == 200
        donnees = reponse.json()
        assert donnees["statut"] == "ok"
        assert donnees["base"] is True

    def test_sans_jeton_configure_le_detail_reste_public(self, client, settings):
        """Le défaut assumé : deux booléens, lisibles par la supervision."""
        settings.HEALTHZ_JETON = ""
        donnees = client.get("/healthz").json()
        assert donnees["base"] is True
        assert donnees["cache"] is True

    def test_avec_un_jeton_le_detail_se_ferme_mais_pas_la_sonde(self, client, settings):
        """
        Ce qui mérite d'être protégé n'est pas l'existence d'une panne — un 503
        la révèle — mais sa nature : dire « la base répond, le cache non »
        renseigne un attaquant sur ce qu'il vient de faire tomber.
        """
        settings.HEALTHZ_JETON = "jeton-de-supervision"

        anonyme = client.get("/healthz")
        assert anonyme.status_code == 200, "La supervision doit continuer à lire le code de réponse"
        assert anonyme.json() == {"statut": "ok"}

        supervise = client.get("/healthz", HTTP_X_HEALTHZ_TOKEN="jeton-de-supervision")
        assert supervise.json()["base"] is True
        assert supervise.json()["cache"] is True

    def test_un_jeton_errone_n_ouvre_pas_le_detail(self, client, settings):
        settings.HEALTHZ_JETON = "jeton-de-supervision"
        donnees = client.get("/healthz", HTTP_X_HEALTHZ_TOKEN="presque-le-bon").json()
        assert donnees == {"statut": "ok"}

    def test_page_404_a_la_charte(self, client):
        reponse = client.get("/cette-page-n-existe-pas/")
        assert reponse.status_code == 404
        contenu = reponse.content.decode()
        assert "Page introuvable" in contenu
        # Aucune trace technique ne doit filtrer vers le visiteur.
        assert "Traceback" not in contenu
        assert "DEBUG" not in contenu


@pytest.mark.django_db
class TestTachesPurge:
    def test_purge_des_notifications_lues(self, etudiant):
        from datetime import timedelta

        from django.utils import timezone

        from apps.core.tasks import purger_notifications

        ancienne = service_notifications.notifier(etudiant, "Ancienne")
        ancienne.marquer_lue()
        Notification.objects.filter(pk=ancienne.pk).update(date_lecture=timezone.now() - timedelta(days=200))
        recente = service_notifications.notifier(etudiant, "Récente")

        assert purger_notifications(jours=120) == 1
        assert Notification.objects.filter(pk=recente.pk).exists()
        assert not Notification.objects.filter(pk=ancienne.pk).exists()

    def test_purge_des_sessions_expirees(self, db):
        """La table des sessions est écrite à chaque requête et ne se vide pas seule."""
        from datetime import timedelta

        from django.contrib.sessions.backends.db import SessionStore
        from django.contrib.sessions.models import Session
        from django.utils import timezone

        from apps.core.tasks import purger_sessions

        expiree = SessionStore()
        expiree["qui"] = "parti depuis longtemps"
        expiree.create()
        Session.objects.filter(session_key=expiree.session_key).update(expire_date=timezone.now() - timedelta(days=1))

        valide = SessionStore()
        valide["qui"] = "encore là"
        valide.create()

        assert purger_sessions() == 1
        assert not Session.objects.filter(session_key=expiree.session_key).exists()
        assert Session.objects.filter(session_key=valide.session_key).exists()

    def test_la_purge_des_sessions_est_programmee(self, settings):
        """Une tâche que rien ne déclenche ne purge rien."""
        planifiee = settings.CELERY_BEAT_SCHEDULE.values()
        assert any(entree["task"] == "core.purger_sessions" for entree in planifiee)
