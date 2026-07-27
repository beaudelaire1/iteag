from decimal import Decimal
from unittest import mock
from uuid import uuid4

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse

from apps.accounts.models import User
from apps.commerce import panier, services
from apps.commerce.forms import ProduitLivreForm
from apps.commerce.models import AlerteStock, Commande, MouvementStock, ProduitLivre


@pytest.fixture
def livre(db):
    return ProduitLivre.objects.create(
        titre="Introduction à la théologie",
        slug="introduction-theologie",
        sku="LIV-001",
        isbn="9780000000001",
        auteur="Auteur Test",
        prix_ttc=Decimal("19.90"),
        stock_physique=5,
        seuil_alerte=2,
    )


def donnees_commande():
    return {
        "prenom": "Marie",
        "nom": "Test",
        "email": "marie@example.com",
        "telephone": "0590000000",
        "adresse": "1 rue de la Paix",
        "complement_adresse": "",
        "code_postal": "97100",
        "ville": "Basse-Terre",
        "pays": "Guadeloupe",
        "mode_paiement": Commande.ModePaiement.VIREMENT,
        "commentaire": "",
    }


def creer_depuis_session(client, livre, quantite=2):
    reponse = client.post(
        reverse("commerce:panier_ajouter", args=[livre.pk]),
        {"quantite": quantite},
    )
    lignes, _ = panier.details(reponse.wsgi_request)
    with mock.patch("apps.commerce.services._notification_commande"):
        return services.creer_commande(
            donnees=donnees_commande(),
            lignes_panier=lignes,
        )


@pytest.mark.django_db
class TestBoutiquePublique:
    def test_catalogue_et_fiche_sont_publics(self, client, livre):
        catalogue = client.get(reverse("commerce:catalogue"))
        fiche = client.get(livre.get_absolute_url())

        assert catalogue.status_code == 200
        assert fiche.status_code == 200
        assert livre.titre in catalogue.content.decode()

    def test_panier_refuse_un_livre_hors_stock(self, client, livre):
        livre.stock_physique = 0
        livre.save(update_fields=["stock_physique"])

        reponse = client.post(
            reverse("commerce:panier_ajouter", args=[livre.pk]),
            {"quantite": 1},
            follow=True,
        )

        assert "plus disponible" in reponse.content.decode()
        assert panier.nombre_articles(reponse.wsgi_request) == 0

    def test_ancienne_url_elearning_redirige(self, client):
        reponse = client.get("/formations-video/un-module/?source=ancien")
        assert reponse.status_code == 301
        assert reponse["Location"] == "/e-learning/un-module/?source=ancien"


@pytest.mark.django_db
class TestCommande:
    def test_le_formulaire_de_commande_affiche_ses_champs(self, client, livre):
        reponse_ajout = client.post(
            reverse("commerce:panier_ajouter", args=[livre.pk]),
            {"quantite": 1},
        )

        reponse = client.get(
            reverse("commerce:commander"),
            follow=True,
        )
        contenu = reponse.content.decode()

        assert reponse_ajout.status_code == 302
        assert 'name="prenom"' in contenu
        assert 'name="adresse"' in contenu
        assert 'name="mode_paiement"' in contenu
        assert 'name="accepte_conditions"' in contenu

    def test_commande_reserve_le_stock_et_cree_un_suivi(self, client, livre):
        commande = creer_depuis_session(client, livre, quantite=2)
        livre.refresh_from_db()

        assert commande.total_produits == Decimal("39.80")
        assert commande.total == Decimal("39.80")
        assert livre.stock_physique == 5
        assert livre.stock_reserve == 2
        assert MouvementStock.objects.filter(
            produit=livre,
            commande=commande,
            type_mouvement=MouvementStock.Type.RESERVATION,
            variation_reserve=2,
        ).exists()
        assert client.get(commande.get_absolute_url()).status_code == 200
        assert client.get(reverse("commerce:commande_suivi", kwargs={"jeton": uuid4()})).status_code == 404

    def test_expedition_sort_le_stock_une_seule_fois(self, client, livre):
        commande = creer_depuis_session(client, livre)
        services.confirmer_commande(commande)
        services.preparer_commande(commande)
        services.expedier_commande(
            commande,
            transporteur="La Poste",
            numero_suivi="FR123",
            url_suivi="https://example.com/suivi/FR123",
        )
        commande.refresh_from_db()
        livre.refresh_from_db()

        assert commande.statut == Commande.Statut.EXPEDIEE
        assert commande.stock_sorti is True
        assert livre.stock_physique == 3
        assert livre.stock_reserve == 0
        assert (
            MouvementStock.objects.filter(
                commande=commande,
                type_mouvement=MouvementStock.Type.SORTIE,
            ).count()
            == 1
        )
        with pytest.raises(ValidationError):
            services.expedier_commande(commande)

    def test_annulation_libere_la_reservation(self, client, livre):
        commande = creer_depuis_session(client, livre, quantite=3)

        services.annuler_commande(commande)
        livre.refresh_from_db()
        commande.refresh_from_db()

        assert commande.statut == Commande.Statut.ANNULEE
        assert livre.stock_physique == 5
        assert livre.stock_reserve == 0

    def test_stock_revalide_au_moment_de_commander(self, client, livre):
        reponse = client.post(
            reverse("commerce:panier_ajouter", args=[livre.pk]),
            {"quantite": 3},
        )
        lignes, _ = panier.details(reponse.wsgi_request)
        livre.stock_physique = 2
        livre.save(update_fields=["stock_physique"])

        with pytest.raises(ValidationError, match="Stock insuffisant"):
            services.creer_commande(
                donnees=donnees_commande(),
                lignes_panier=lignes,
            )


@pytest.mark.django_db
class TestStockEtAlertes:
    def test_stock_initial_est_saisissable_mais_une_modification_passe_par_l_ajustement(
        self,
        livre,
    ):
        creation = ProduitLivreForm()
        modification = ProduitLivreForm(instance=livre)

        assert creation.fields["stock_physique"].disabled is False
        assert modification.fields["stock_physique"].disabled is True

    def test_alerte_s_ouvre_puis_se_resout_apres_reassort(self, livre):
        services.ajuster_stock(livre, -3, "Inventaire")
        alerte = AlerteStock.objects.get(produit=livre, resolue=False)
        assert alerte.stock_disponible_detecte == 2

        services.ajuster_stock(livre, 3, "Réassort")
        alerte.refresh_from_db()
        assert alerte.resolue is True
        assert alerte.date_resolution is not None

    def test_un_ajustement_ne_peut_pas_entamer_le_stock_reserve(self, client, livre):
        creer_depuis_session(client, livre, quantite=4)

        with pytest.raises(ValidationError, match="réservés"):
            services.ajuster_stock(livre, -2, "Mauvais comptage")

    def test_la_gestion_est_reservee_au_personnel(self, client, livre):
        etudiant = User.objects.create_user(
            username="client-boutique",
            password="motdepasse-long-12",
            role=User.Role.ETUDIANT,
        )
        client.force_login(etudiant)
        assert client.get(reverse("commerce:gestion_stock")).status_code == 403
