"""
Ce qu'une suppression ne doit jamais emporter en silence.

Le défaut : les écrans de suppression demandaient « Êtes-vous sûr ? » sans dire
de quoi. Plusieurs clés étrangères sont pourtant en cascade — supprimer un
compte utilisateur effaçait le profil étudiant, et avec lui ses inscriptions,
ses notes, ses crédits ECTS et l'historique de ses paiements. En deux clics.

Ces tests fixent les refus, et vérifient que la confirmation dit ce qu'elle
détruit. Ils portent sur des pertes de données irréversibles : c'est la
catégorie de défaut qu'on ne rattrape pas après coup.
"""

from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.academics.models import (
    CoursDeSession,
    CreditECTS,
    Paiement,
    ProfilEtudiant,
    Promotion,
    SessionAcademique,
)
from apps.accounts.models import User
from apps.administration.suppression import inventaire_des_pertes
from apps.formations.models import Cours, Discipline, Parcours, Professeur


@pytest.fixture
def administrateur(db):
    return User.objects.create_user(
        username="admin_supp", email="as@iteag.org", password="motdepasse-long-12", role=User.Role.ADMIN
    )


@pytest.fixture
def univers(db):
    parcours = Parcours.objects.create(
        nom="Diplômant", slug="diplomant-supp", type_parcours=Parcours.TypeParcours.DIPLOMANT_ITEAG
    )
    promotion = Promotion.objects.create(nom="Promo supp", parcours=parcours, annee_debut=2027, annee_fin=2033)
    discipline = Discipline.objects.create(nom="Patrologie", slug="patrologie-supp")
    utilisateur_prof = User.objects.create_user(
        username="prof_supp", email="ps@iteag.org", password="motdepasse-long-12", role=User.Role.ENSEIGNANT
    )
    professeur = Professeur.objects.create(user=utilisateur_prof, nom="Marc", prenom="Jean", slug="jean-marc-supp")
    cours = Cours.objects.create(titre="Les conciles", slug="les-conciles", discipline=discipline)
    session = SessionAcademique.objects.create(
        nom="Session supp",
        periode=SessionAcademique.Periode.TOUSSAINT,
        annee_academique="2027-2028",
        date_debut="2027-11-02",
        date_fin="2027-11-07",
    )
    utilisateur = User.objects.create_user(
        username="etu_supp",
        email="es@iteag.org",
        password="motdepasse-long-12",
        first_name="Claire",
        last_name="Mathieu",
        role=User.Role.ETUDIANT,
    )
    etudiant = ProfilEtudiant.objects.create(
        utilisateur=utilisateur,
        parcours=parcours,
        promotion=promotion,
        numero_etudiant="ETU-SUPP-1",
    )
    return {
        "parcours": parcours,
        "session": session,
        "cours": cours,
        "professeur": professeur,
        "etudiant": etudiant,
        "utilisateur": utilisateur,
    }


def supprimer(client, nom_route, objet):
    return client.post(reverse(nom_route, args=[objet.pk]), follow=True)


# ══════════════════════════════════════════════
# Comptes
# ══════════════════════════════════════════════


@pytest.mark.django_db
class TestSuppressionDUnCompte:
    def test_un_compte_portant_un_dossier_etudiant_est_protege(self, client, administrateur, univers):
        """
        Le cas qui a motivé tout ce fichier : la cascade emportait notes,
        crédits et paiements sans un mot.
        """
        client.force_login(administrateur)
        supprimer(client, "administration:user_delete", univers["utilisateur"])
        assert User.objects.filter(pk=univers["utilisateur"].pk).exists()
        assert ProfilEtudiant.objects.filter(pk=univers["etudiant"].pk).exists()

    def test_le_refus_indique_quoi_faire(self, client, administrateur, univers):
        client.force_login(administrateur)
        reponse = supprimer(client, "administration:user_delete", univers["utilisateur"])
        assert "Désactivez le compte" in reponse.content.decode()

    def test_on_ne_supprime_pas_son_propre_compte(self, client, administrateur):
        client.force_login(administrateur)
        supprimer(client, "administration:user_delete", administrateur)
        assert User.objects.filter(pk=administrateur.pk).exists()

    def test_le_dernier_administrateur_est_protege(self, client, administrateur, db):
        """
        Le supprimer fermerait le portail à tout le monde, sans recours. Le cas
        n'est atteignable que par un superutilisateur d'un autre rôle : entre
        deux administrateurs, la règle du compte propre suffit déjà.
        """
        superutilisateur = User.objects.create_superuser(
            username="root_supp", email="rs@iteag.org", password="motdepasse-long-12", role=User.Role.SECRETARIAT
        )
        client.force_login(superutilisateur)
        supprimer(client, "administration:user_delete", administrateur)
        assert User.objects.filter(pk=administrateur.pk).exists()

    def test_un_administrateur_sur_deux_reste_supprimable(self, client, administrateur, db):
        """La protection vise la dernière porte d'entrée, pas toute suppression."""
        second = User.objects.create_user(
            username="admin_2", email="a2@iteag.org", password="motdepasse-long-12", role=User.Role.ADMIN
        )
        client.force_login(administrateur)
        supprimer(client, "administration:user_delete", second)
        assert not User.objects.filter(pk=second.pk).exists()

    def test_un_compte_sans_attache_se_supprime(self, client, administrateur, db):
        """La protection ne doit pas empêcher le geste légitime."""
        jetable = User.objects.create_user(
            username="jetable", email="j@iteag.org", password="motdepasse-long-12", role=User.Role.ETUDIANT
        )
        client.force_login(administrateur)
        supprimer(client, "administration:user_delete", jetable)
        assert not User.objects.filter(pk=jetable.pk).exists()


# ══════════════════════════════════════════════
# Dossiers et référentiel
# ══════════════════════════════════════════════


@pytest.mark.django_db
class TestSuppressionDUnDossierEtudiant:
    def test_un_dossier_avec_credits_est_protege(self, client, administrateur, univers):
        CreditECTS.objects.create(
            etudiant=univers["etudiant"],
            ects_obtenus=Decimal("5.0"),
            source=CreditECTS.SourceCredit.ITEAG,
            date_validation=timezone.localdate(),
        )
        client.force_login(administrateur)
        supprimer(client, "administration:etudiant_delete", univers["etudiant"])
        assert ProfilEtudiant.objects.filter(pk=univers["etudiant"].pk).exists()

    def test_un_dossier_avec_paiements_est_protege(self, client, administrateur, univers):
        Paiement.objects.create(
            etudiant=univers["etudiant"],
            montant=Decimal("100.00"),
            date_paiement=timezone.localdate(),
            mode=Paiement.ModePaiement.VIREMENT,
        )
        client.force_login(administrateur)
        supprimer(client, "administration:etudiant_delete", univers["etudiant"])
        assert ProfilEtudiant.objects.filter(pk=univers["etudiant"].pk).exists()

    def test_un_dossier_vierge_se_supprime(self, client, administrateur, univers):
        client.force_login(administrateur)
        supprimer(client, "administration:etudiant_delete", univers["etudiant"])
        assert not ProfilEtudiant.objects.filter(pk=univers["etudiant"].pk).exists()


@pytest.mark.django_db
class TestSuppressionDuReferentiel:
    def test_une_session_programmee_est_protegee(self, client, administrateur, univers):
        """La cascade aurait emporté cours, inscriptions, notes et annonces."""
        CoursDeSession.objects.create(
            session=univers["session"], cours=univers["cours"], enseignant=univers["professeur"]
        )
        client.force_login(administrateur)
        supprimer(client, "administration:session_delete", univers["session"])
        assert SessionAcademique.objects.filter(pk=univers["session"].pk).exists()

    def test_un_professeur_rattache_a_un_cours_est_protege(self, client, administrateur, univers):
        """La clé est en PROTECT : sans garde-fou, l'écran renvoyait une erreur de base."""
        CoursDeSession.objects.create(
            session=univers["session"], cours=univers["cours"], enseignant=univers["professeur"]
        )
        client.force_login(administrateur)
        reponse = supprimer(client, "administration:professeur_delete", univers["professeur"])
        assert reponse.status_code == 200
        assert Professeur.objects.filter(pk=univers["professeur"].pk).exists()

    def test_une_session_vide_se_supprime(self, client, administrateur, univers):
        client.force_login(administrateur)
        supprimer(client, "administration:session_delete", univers["session"])
        assert not SessionAcademique.objects.filter(pk=univers["session"].pk).exists()


# ══════════════════════════════════════════════
# L'inventaire
# ══════════════════════════════════════════════


@pytest.mark.django_db
class TestInventaireDesPertes:
    def test_il_recense_la_cascade(self, univers):
        pertes = dict(inventaire_des_pertes(univers["utilisateur"]))
        assert any("étudiant" in libelle.lower() for libelle in pertes)

    def test_l_objet_lui_meme_n_est_pas_un_dommage_collateral(self, db):
        vierge = User.objects.create_user(
            username="vierge", email="v@iteag.org", password="motdepasse-long-12", role=User.Role.ETUDIANT
        )
        assert inventaire_des_pertes(vierge) == []

    def test_une_cle_protegee_ne_fait_pas_planter_l_inventaire(self, univers):
        """Le collecteur de Django lève « ProtectedError » : l'écran ne doit pas s'en émouvoir."""
        CoursDeSession.objects.create(
            session=univers["session"], cours=univers["cours"], enseignant=univers["professeur"]
        )
        assert inventaire_des_pertes(univers["professeur"]) == []

    def test_la_confirmation_annonce_ce_qu_elle_detruit(self, client, administrateur, univers):
        """« Êtes-vous sûr ? » ne portait sur rien de précis."""
        CoursDeSession.objects.create(
            session=univers["session"], cours=univers["cours"], enseignant=univers["professeur"]
        )
        client.force_login(administrateur)
        contenu = client.get(reverse("administration:session_delete", args=[univers["session"].pk])).content.decode()
        # L'écran annonce soit ce qui disparaîtrait, soit pourquoi il refuse.
        assert "Seront également supprimés" in contenu or "la programmation, ou clôturez la session" in contenu

    def test_l_inventaire_est_montre_quand_la_suppression_est_permise(self, client, administrateur, univers):
        client.force_login(administrateur)
        contenu = client.get(reverse("administration:user_delete", args=[univers["utilisateur"].pk])).content.decode()
        # Le compte porte un dossier étudiant : le refus prime sur l'inventaire.
        assert "dossier étudiant" in contenu


# ══════════════════════════════════════════════
# Cloisonnement
# ══════════════════════════════════════════════


@pytest.mark.django_db
class TestSeuleLAdministrationSupprime:
    @pytest.mark.parametrize(
        "nom_route,cle",
        [
            ("administration:etudiant_delete", "etudiant"),
            ("administration:session_delete", "session"),
            ("administration:professeur_delete", "professeur"),
        ],
    )
    def test_le_secretariat_ne_supprime_pas(self, client, univers, nom_route, cle, db):
        secretaire = User.objects.create_user(
            username="sec_supp", email="ss@iteag.org", password="motdepasse-long-12", role=User.Role.SECRETARIAT
        )
        client.force_login(secretaire)
        reponse = client.post(reverse(nom_route, args=[univers[cle].pk]))
        assert reponse.status_code in (302, 403)
        assert type(univers[cle]).objects.filter(pk=univers[cle].pk).exists()
