"""
Ce que la barre montre à qui est connecté.

Deux défauts, tous deux visibles à l'œil nu et qu'aucun test ne relevait :

1. **les initiales s'affichaient « …… »** — `truncatechars:1` ne coupe pas à un
   caractère, il rend l'ellipse, qui compte pour le caractère autorisé. La
   pastille de l'utilisateur, celle des fiches professeurs et celle de la
   colonne des portails affichaient toutes le même « … » ;
2. **la cloche des notifications n'existait nulle part** — le modèle, le
   service, la page « /notifications/ » et le compteur poussé dans le contexte
   de chaque page étaient en place, mais aucune barre n'y menait. On ne pouvait
   apprendre qu'on avait été notifié qu'en devinant l'adresse.
"""

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.accounts.models import User
from apps.core.services.notifications import notifier


@pytest.fixture
def etudiant(db):
    return User.objects.create_user(
        username="jdupont",
        email="jdupont@iteag.org",
        password="motdepasse-long-12",
        first_name="Jean",
        last_name="Dupont",
        role=User.Role.ETUDIANT,
    )


@pytest.mark.django_db
class TestLesInitiales:
    def test_la_pastille_montre_les_initiales(self, client, etudiant):
        client.force_login(etudiant)
        contenu = client.get(reverse("elearning:catalogue")).content.decode()
        assert "JD" in contenu, "Les initiales ne sont pas rendues"

    def test_aucune_ellipse_a_la_place_des_initiales(self, client, etudiant):
        client.force_login(etudiant)
        contenu = client.get(reverse("elearning:catalogue")).content.decode()
        assert "…" not in contenu, "« truncatechars:1 » rend l'ellipse, pas la première lettre"

    def test_les_initiales_sont_en_capitales(self, client, db):
        """Une saisie en minuscules ne doit pas descendre dans la pastille."""
        utilisateur = User.objects.create_user(
            username="mnoel",
            email="mnoel@iteag.org",
            password="motdepasse-long-12",
            first_name="marie",
            last_name="noël",
            role=User.Role.ETUDIANT,
        )
        client.force_login(utilisateur)
        assert "MN" in client.get(reverse("elearning:catalogue")).content.decode()


@pytest.mark.django_db
class TestLaCloche:
    def test_la_barre_mene_aux_notifications(self, client, etudiant):
        client.force_login(etudiant)
        contenu = client.get(reverse("elearning:catalogue")).content.decode()
        assert reverse("core:notifications") in contenu, "Aucun chemin vers les notifications"

    def test_le_compteur_parait_quand_il_y_a_du_non_lu(self, client, etudiant):
        for i in range(3):
            notifier(etudiant, f"Annonce {i}")
        client.force_login(etudiant)
        contenu = client.get(reverse("elearning:catalogue")).content.decode()
        assert "nav-cloche-pastille" in contenu
        assert "3 non lues" in contenu, "Le nombre doit être annoncé, pas seulement dessiné"

    def test_aucune_pastille_sans_notification(self, client, etudiant):
        client.force_login(etudiant)
        contenu = client.get(reverse("elearning:catalogue")).content.decode()
        assert "nav-cloche" in contenu, "La cloche reste, seule la pastille disparaît"
        assert "nav-cloche-pastille" not in contenu

    def test_le_compteur_est_plafonne(self, client, etudiant):
        """Au-delà de neuf, le nombre exact déborderait la pastille."""
        for i in range(12):
            notifier(etudiant, f"Annonce {i}")
        client.force_login(etudiant)
        contenu = client.get(reverse("elearning:catalogue")).content.decode()
        assert "9+" in contenu
        assert "12 non lues" in contenu, "Le nombre exact reste annoncé au lecteur d'écran"

    def test_le_visiteur_anonyme_ne_voit_pas_de_cloche(self, client):
        contenu = client.get(reverse("elearning:catalogue")).content.decode()
        assert "nav-cloche" not in contenu

    def test_le_compteur_n_est_calcule_qu_une_fois_par_page(self, client, etudiant):
        """La barre de bureau et le menu mobile affichent la même cloche.

        Chacun résout « notifications_non_lues » pour son propre rendu : sans
        mémorisation, la même page compterait deux fois les non-lues en base.
        """
        notifier(etudiant, "Annonce")
        client.force_login(etudiant)

        with CaptureQueriesContext(connection) as requetes:
            client.get(reverse("elearning:catalogue"))

        comptages = [
            requete["sql"]
            for requete in requetes.captured_queries
            if "core_notification" in requete["sql"] and "COUNT" in requete["sql"].upper()
        ]
        assert len(comptages) == 1, f"{len(comptages)} comptages de notifications pour une seule page"
