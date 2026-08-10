from decimal import Decimal
from unittest import mock
from uuid import uuid4

import pytest
from django.core import mail
from django.core.exceptions import ValidationError
from django.test import override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.commerce import panier, services
from apps.commerce.forms import ProduitLivreForm
from apps.commerce.models import (
    AlerteStock,
    Commande,
    DestinationLivraison,
    MouvementStock,
    ProduitLivre,
    TarifLivraison,
    TypeLivraison,
)
from apps.paiements.models import Reglement
from apps.paiements.services import reglements, webhook


@pytest.fixture
def secretaire(db):
    return User.objects.create_user(
        username="sec_commerce",
        email="sec_commerce@iteag.org",
        password="motdepasse-long-12",
        role=User.Role.SECRETARIAT,
    )


@pytest.fixture
def livre(db):
    # Les tests métier utilisent une grille minimale maîtrisée ; la migration
    # charge par ailleurs le barème public complet pour l'application réelle.
    TarifLivraison.objects.all().delete()
    TarifLivraison.objects.create(
        destination=DestinationLivraison.GUADELOUPE,
        type_livraison=TypeLivraison.STANDARD,
        poids_max_grammes=5000,
        prix_ttc=Decimal("10.00"),
    )
    return ProduitLivre.objects.create(
        titre="Introduction à la théologie",
        slug="introduction-theologie",
        sku="LIV-001",
        isbn="9780000000001",
        auteur="Auteur Test",
        prix_ttc=Decimal("19.90"),
        poids_grammes=400,
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
        "type_livraison": TypeLivraison.STANDARD,
        "mode_paiement": Commande.ModePaiement.VIREMENT,
        "commentaire": "",
    }


def donnees_formulaire_commande(mode_paiement):
    return donnees_commande() | {
        "mode_paiement": mode_paiement,
        "accepte_conditions": "on",
        "site_web": "",
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
def test_la_migration_charge_les_baremes_officiels_laposte_2026():
    assert TarifLivraison.objects.count() == 205

    attendus = {
        (DestinationLivraison.GUADELOUPE, TypeLivraison.STANDARD, 500): Decimal("7.59"),
        (DestinationLivraison.MARTINIQUE, TypeLivraison.STANDARD, 500): Decimal("7.59"),
        (DestinationLivraison.GUYANE, TypeLivraison.STANDARD, 500): Decimal("10.02"),
        (DestinationLivraison.GUADELOUPE, TypeLivraison.EXPRESS, 30000): Decimal("58.18"),
        (DestinationLivraison.MARTINIQUE, TypeLivraison.EXPRESS, 12000): Decimal("71.01"),
        (DestinationLivraison.GUYANE, TypeLivraison.EXPRESS, 12000): Decimal("71.01"),
    }
    for (destination, type_livraison, poids), prix in attendus.items():
        tarif = TarifLivraison.objects.get(
            destination=destination,
            type_livraison=type_livraison,
            poids_max_grammes=poids,
        )
        assert tarif.prix_ttc == prix
        assert tarif.source_url.startswith("https://www.laposte.fr/")
        assert tarif.date_effet.isoformat() == "2026-04-01"


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
        assert 'name="pays"' in contenu
        assert 'name="type_livraison"' in contenu
        assert 'name="mode_paiement"' in contenu
        assert 'name="accepte_conditions"' in contenu
        # La case engage le client : le document qu'elle vise doit être
        # atteignable depuis le tunnel, sinon le consentement porte sur rien.
        assert reverse("website:conditions_generales_vente") in contenu
        assert "conditions générales de vente</a>" in contenu
        assert reverse("commerce:devis_livraison") in contenu
        assert "commerce-commande.js?v=20260729-2" in contenu
        assert 'id="source-tarif-livraison"' in contenu

    def test_commande_reserve_le_stock_et_cree_un_suivi(self, client, livre):
        commande = creer_depuis_session(client, livre, quantite=2)
        livre.refresh_from_db()

        assert commande.total_produits == Decimal("39.80")
        assert commande.poids_total_grammes == 800
        assert commande.frais_livraison == Decimal("10.00")
        assert commande.total == Decimal("49.80")
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

    def test_creation_envoie_une_confirmation_complete(
        self,
        client,
        livre,
        django_capture_on_commit_callbacks,
    ):
        reponse = client.post(reverse("commerce:panier_ajouter", args=[livre.pk]), {"quantite": 2})
        lignes, _ = panier.details(reponse.wsgi_request)
        mail.outbox.clear()

        with django_capture_on_commit_callbacks(execute=True):
            commande = services.creer_commande(donnees=donnees_commande(), lignes_panier=lignes)

        assert len(mail.outbox) == 1
        assert commande.numero in mail.outbox[0].subject
        assert commande.numero in mail.outbox[0].body
        assert "49.80" in mail.outbox[0].body

    def test_confirmation_du_paiement_envoie_le_nouveau_statut(
        self,
        client,
        livre,
        django_capture_on_commit_callbacks,
    ):
        commande = creer_depuis_session(client, livre)
        mail.outbox.clear()

        with django_capture_on_commit_callbacks(execute=True):
            services.confirmer_commande(commande)

        assert len(mail.outbox) == 1
        assert "confirmée" in mail.outbox[0].subject.lower()
        assert "règlement a été confirmé" in mail.outbox[0].body

    def test_devis_depend_de_la_destination_et_du_type_de_livraison(self, client, livre):
        tarifs = {
            (DestinationLivraison.GUADELOUPE, TypeLivraison.STANDARD): Decimal("10.00"),
            (DestinationLivraison.GUADELOUPE, TypeLivraison.EXPRESS): Decimal("18.00"),
            (DestinationLivraison.GUYANE, TypeLivraison.STANDARD): Decimal("12.00"),
            (DestinationLivraison.GUYANE, TypeLivraison.EXPRESS): Decimal("22.00"),
            (DestinationLivraison.MARTINIQUE, TypeLivraison.STANDARD): Decimal("11.00"),
            (DestinationLivraison.MARTINIQUE, TypeLivraison.EXPRESS): Decimal("19.00"),
        }
        for (destination, type_livraison), prix in tarifs.items():
            TarifLivraison.objects.update_or_create(
                destination=destination,
                type_livraison=type_livraison,
                poids_max_grammes=5000,
                defaults={"prix_ttc": prix, "actif": True},
            )
        client.post(reverse("commerce:panier_ajouter", args=[livre.pk]), {"quantite": 1})

        for (destination, type_livraison), prix in tarifs.items():
            reponse = client.get(
                reverse("commerce:devis_livraison"),
                {"destination": destination, "type_livraison": type_livraison},
            )
            contenu = reponse.json()
            assert reponse.status_code == 200
            assert contenu["frais_livraison"] == str(prix)
            assert contenu["total_commande"] == str(Decimal("19.90") + prix)
            assert contenu["poids_grammes"] == 400

    def test_retrait_sur_place_devis_et_commande(self, client, livre):
        client.post(reverse("commerce:panier_ajouter", args=[livre.pk]), {"quantite": 1})
        reponse = client.get(
            reverse("commerce:devis_livraison"),
            {"destination": "Guadeloupe", "type_livraison": TypeLivraison.RETRAIT_SUR_PLACE},
        )
        assert reponse.status_code == 200
        donnees = reponse.json()
        assert donnees["disponible"] is True
        assert donnees["frais_livraison"] == "0.00"
        assert donnees["total_commande"] == "19.90"

        lignes, _ = panier.details(reponse.wsgi_request)
        donnees_cmd = donnees_commande() | {"type_livraison": TypeLivraison.RETRAIT_SUR_PLACE}
        cmd = services.creer_commande(donnees=donnees_cmd, lignes_panier=lignes)
        assert cmd.frais_livraison == Decimal("0.00")
        assert cmd.total == Decimal("19.90")
        assert cmd.type_livraison == TypeLivraison.RETRAIT_SUR_PLACE

    def test_remise_etudiant_inscrit(self, client, livre, db):
        from apps.academics.models import ProfilEtudiant, Promotion
        from apps.formations.models import Parcours

        user_etudiant = User.objects.create_user(
            username="etu_remise",
            email="etudiant@iteag.org",
            password="password123!",
            role=User.Role.ETUDIANT,
        )
        parcours = Parcours.objects.create(nom="Bachelor", slug="bachelor-test", type_parcours="bachelor_flte")
        promotion = Promotion.objects.create(nom="Promo 2026", parcours=parcours, annee_debut=2026, annee_fin=2027)
        ProfilEtudiant.objects.create(utilisateur=user_etudiant, parcours=parcours, promotion=promotion)

        client.post(reverse("commerce:panier_ajouter", args=[livre.pk]), {"quantite": 2})  # 39.80 total
        lignes, _ = panier.details(client.get(reverse("commerce:panier")).wsgi_request)

        # Utilisateur connecté en tant qu'étudiant
        cmd = services.creer_commande(donnees=donnees_commande(), lignes_panier=lignes, utilisateur=user_etudiant)
        # 39.80 * 10% = 3.98 remise, frais = 10.00 -> total = 39.80 - 3.98 + 10.00 = 45.82
        assert cmd.total_produits == Decimal("39.80")
        assert cmd.remise == Decimal("3.98")
        assert cmd.frais_livraison == Decimal("10.00")
        assert cmd.total == Decimal("45.82")

    def test_devis_choisit_le_palier_de_poids_le_plus_precis(self, client, livre):
        TarifLivraison.objects.create(
            destination=DestinationLivraison.GUADELOUPE,
            type_livraison=TypeLivraison.STANDARD,
            poids_max_grammes=500,
            prix_ttc=Decimal("5.00"),
        )
        client.post(reverse("commerce:panier_ajouter", args=[livre.pk]), {"quantite": 1})

        leger = client.get(
            reverse("commerce:devis_livraison"),
            {"destination": "Guadeloupe", "type_livraison": "standard"},
        ).json()
        client.post(reverse("commerce:panier_modifier", args=[livre.pk]), {"quantite": 2})
        lourd = client.get(
            reverse("commerce:devis_livraison"),
            {"destination": "Guadeloupe", "type_livraison": "standard"},
        ).json()

        assert leger["frais_livraison"] == "5.00"
        assert lourd["frais_livraison"] == "10.00"

    def test_aucune_commande_n_est_creee_sans_tarif_contractuel(self, client, livre):
        TarifLivraison.objects.all().delete()
        client.post(reverse("commerce:panier_ajouter", args=[livre.pk]), {"quantite": 1})

        devis = client.get(
            reverse("commerce:devis_livraison"),
            {"destination": "Guyane", "type_livraison": "express"},
        )
        commande = client.post(
            reverse("commerce:commander"),
            donnees_formulaire_commande(Commande.ModePaiement.CARTE) | {"pays": "Guyane", "type_livraison": "express"},
        )

        assert devis.status_code == 422
        assert devis.json()["disponible"] is False
        assert commande.status_code == 200
        assert "Aucun tarif express" in commande.content.decode()
        assert Commande.objects.exists() is False

    def test_livraison_n_est_offerte_qu_a_partir_de_cent_cinquante_euros(self, client, livre):
        livre.prix_ttc = Decimal("149.00")
        livre.save(update_fields=["prix_ttc", "updated_at"])
        sous_seuil = creer_depuis_session(client, livre, quantite=1)

        assert sous_seuil.frais_livraison == Decimal("10.00")
        assert sous_seuil.total == Decimal("159.00")

        services.annuler_commande(sous_seuil, motif=Commande.MotifAnnulation.DEMANDE_CLIENT)
        session = client.session
        session.pop(panier.CLE_SESSION, None)
        session.save()
        livre.prix_ttc = Decimal("150.00")
        livre.save(update_fields=["prix_ttc", "updated_at"])
        au_seuil = creer_depuis_session(client, livre, quantite=1)

        assert au_seuil.frais_livraison == Decimal("0.00")
        assert au_seuil.total == Decimal("150.00")

    def test_suivant_ouvre_immediatement_le_paiement_integre_pour_la_carte(self, client, livre):
        client.post(reverse("commerce:panier_ajouter", args=[livre.pk]), {"quantite": 2})

        with mock.patch("apps.commerce.services._notification_commande"):
            reponse = client.post(
                reverse("commerce:commander"),
                donnees_formulaire_commande(Commande.ModePaiement.CARTE),
            )

        commande = Commande.objects.get()
        assert reponse.status_code == 307
        assert reponse.url == reverse("paiements:payer_commande", args=[commande.jeton_suivi])
        assert panier.CLE_SESSION not in client.session

        paiement = client.post(reponse.url)

        assert paiement.status_code == 302
        reglement = Reglement.objects.get(commande=commande)
        assert paiement.url == reverse("paiements:checkout", args=[reglement.pk])
        assert commande.frais_livraison == Decimal("10.00")
        assert reglement.montant_ttc == commande.total

        page = client.get(paiement.url)
        contenu = page.content.decode()
        assert page.status_code == 200
        assert commande.numero in contenu
        assert "Livraison standard" in contenu
        assert "49,80" in contenu or "49.80" in contenu

    def test_virement_va_au_suivi_sans_ouvrir_stripe(self, client, livre):
        client.post(reverse("commerce:panier_ajouter", args=[livre.pk]), {"quantite": 1})

        with mock.patch("apps.commerce.services._notification_commande"):
            reponse = client.post(
                reverse("commerce:commander"),
                donnees_formulaire_commande(Commande.ModePaiement.VIREMENT),
            )

        commande = Commande.objects.get()
        assert reponse.status_code == 302
        assert reponse.url == commande.get_absolute_url()
        assert Reglement.objects.filter(commande=commande).exists() is False

    def test_le_suivi_permet_de_reprendre_un_paiement_carte(self, client, livre):
        donnees = donnees_commande() | {"mode_paiement": Commande.ModePaiement.CARTE}
        reponse = client.post(reverse("commerce:panier_ajouter", args=[livre.pk]), {"quantite": 1})
        lignes, _ = panier.details(reponse.wsgi_request)
        with mock.patch("apps.commerce.services._notification_commande"):
            commande = services.creer_commande(donnees=donnees, lignes_panier=lignes)

        contenu = client.get(commande.get_absolute_url()).content.decode()
        assert reverse("paiements:payer_commande", args=[commande.jeton_suivi]) in contenu
        assert "Payer " in contenu
        assert " par carte" in contenu

    def test_un_get_ne_cree_jamais_de_session_stripe(self, client, livre):
        donnees = donnees_commande() | {"mode_paiement": Commande.ModePaiement.CARTE}
        commande = creer_depuis_session(client, livre)
        commande.mode_paiement = donnees["mode_paiement"]
        commande.save(update_fields=["mode_paiement", "updated_at"])

        reponse = client.get(reverse("paiements:payer_commande", args=[commande.jeton_suivi]))

        assert reponse.status_code == 405
        assert Reglement.objects.filter(commande=commande).exists() is False

    def test_le_webhook_stripe_confirme_la_commande_payee(self, client, livre):
        commande = creer_depuis_session(client, livre)
        commande.mode_paiement = Commande.ModePaiement.CARTE
        commande.save(update_fields=["mode_paiement", "updated_at"])
        reglement = reglements.pour_commande(commande)

        webhook.traiter(
            {
                "id": "evt_commande_payee",
                "type": "checkout.session.completed",
                "data": {
                    "object": {
                        "client_reference_id": str(reglement.pk),
                        "payment_status": "paid",
                        "payment_intent": "pi_commande",
                        "amount_total": reglement.montant_en_centimes,
                    }
                },
            }
        )

        commande.refresh_from_db()
        reglement.refresh_from_db()
        assert reglement.statut == Reglement.Statut.PAYE
        assert commande.statut == Commande.Statut.CONFIRMEE
        assert commande.statut_paiement == Commande.StatutPaiement.CONFIRME

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

        services.annuler_commande(commande, motif=Commande.MotifAnnulation.RUPTURE_STOCK)
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

    @override_settings(COMMERCE_ALERTE_EMAIL="stock@example.org")
    def test_alerte_de_stock_envoie_un_email(self, livre, django_capture_on_commit_callbacks):
        mail.outbox.clear()

        with django_capture_on_commit_callbacks(execute=True):
            services.ajuster_stock(livre, -3, "Inventaire")

        assert len(mail.outbox) == 1
        assert mail.outbox[0].to == ["stock@example.org"]
        assert "Stock minimal" in mail.outbox[0].subject
        assert livre.titre in mail.outbox[0].body

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


@pytest.mark.django_db
class TestGestionTarifsLivraison:
    def test_un_admin_saisit_un_tarif_contractuel(self, client):
        administrateur = User.objects.create_user(
            username="admin-tarifs",
            password="motdepasse-long-12",
            role=User.Role.ADMIN,
        )
        client.force_login(administrateur)

        reponse = client.post(
            reverse("commerce:gestion_tarifs_livraison"),
            {
                "destination": DestinationLivraison.GUYANE,
                "type_livraison": TypeLivraison.EXPRESS,
                "poids_max_grammes": 2250,
                "prix_ttc": "24.50",
                "actif": "on",
            },
        )

        assert reponse.status_code == 302
        tarif = TarifLivraison.objects.get(
            destination=DestinationLivraison.GUYANE,
            type_livraison=TypeLivraison.EXPRESS,
            poids_max_grammes=2250,
        )
        assert tarif.destination == DestinationLivraison.GUYANE
        assert tarif.type_livraison == TypeLivraison.EXPRESS
        assert tarif.poids_max_grammes == 2250
        assert tarif.prix_ttc == Decimal("24.50")

    def test_la_grille_tarifaire_est_reservee_aux_admins(self, client):
        secretariat = User.objects.create_user(
            username="secretariat-tarifs",
            password="motdepasse-long-12",
            role=User.Role.SECRETARIAT,
        )
        client.force_login(secretariat)

        reponse = client.get(reverse("commerce:gestion_tarifs_livraison"))

        assert reponse.status_code == 403


@pytest.mark.django_db
class TestMotifAnnulation:
    """Annuler sans dire pourquoi rend les annulations incomptables.

    Une rupture de stock et un client qui se ravise n'appellent pas la même
    réaction — et on ne le saura jamais si chacun écrit sa propre formule dans
    un champ libre, ou si rien n'est demandé du tout.
    """

    def test_le_motif_est_obligatoire(self, client, livre):
        commande = creer_depuis_session(client, livre, quantite=1)
        with pytest.raises(ValidationError):
            services.annuler_commande(commande)
        commande.refresh_from_db()
        assert commande.statut != Commande.Statut.ANNULEE

    def test_un_motif_hors_liste_est_refuse(self, client, livre):
        commande = creer_depuis_session(client, livre, quantite=1)
        with pytest.raises(ValidationError):
            services.annuler_commande(commande, motif="parce que")

    def test_autre_motif_exige_une_precision(self, client, livre):
        """« Autre » sans précision ne dit rien de plus que rien du tout."""
        commande = creer_depuis_session(client, livre, quantite=1)
        with pytest.raises(ValidationError):
            services.annuler_commande(commande, motif=Commande.MotifAnnulation.AUTRE, precision="  ")

        services.annuler_commande(
            commande, motif=Commande.MotifAnnulation.AUTRE, precision="Doublon avec la commande CMD-0012."
        )
        commande.refresh_from_db()
        assert commande.statut == Commande.Statut.ANNULEE
        assert commande.precision_annulation == "Doublon avec la commande CMD-0012."

    def test_le_motif_est_conserve_et_annonce_au_client(self, client, livre, django_capture_on_commit_callbacks):
        commande = creer_depuis_session(client, livre, quantite=1)
        mail.outbox.clear()

        # Le courriel part après validation de la transaction : sans capture,
        # il ne serait jamais envoyé dans un test.
        with django_capture_on_commit_callbacks(execute=True):
            services.annuler_commande(commande, motif=Commande.MotifAnnulation.RUPTURE_STOCK)

        commande.refresh_from_db()
        assert commande.motif_annulation == Commande.MotifAnnulation.RUPTURE_STOCK
        assert commande.get_motif_annulation_display() == "Rupture de stock"
        assert any("Rupture de stock" in message.body for message in mail.outbox), (
            "Le client doit savoir pourquoi sa commande est annulée"
        )

    def test_le_secretariat_annule_depuis_son_ecran(self, client, livre, secretaire):
        commande = creer_depuis_session(client, livre, quantite=1)
        client.force_login(secretaire)

        client.post(
            reverse("commerce:commande_action", args=[commande.pk]),
            {"action": "annuler", "motif_annulation": Commande.MotifAnnulation.ADRESSE_INVALIDE},
        )

        commande.refresh_from_db()
        assert commande.statut == Commande.Statut.ANNULEE
        assert commande.motif_annulation == Commande.MotifAnnulation.ADRESSE_INVALIDE

    def test_l_ecran_propose_la_liste_des_motifs(self, client, livre, secretaire):
        creer_depuis_session(client, livre, quantite=1)
        client.force_login(secretaire)
        contenu = client.get(reverse("commerce:gestion_commandes")).content.decode()
        assert 'name="motif_annulation"' in contenu
        assert "Rupture de stock" in contenu


# ══════════════════════════════════════════════
# Ce que la page de commande doit dire
# ══════════════════════════════════════════════


@pytest.mark.django_db
class TestLaPageDeCommandeDitLaVerite:
    """
    Deux exigences que le prochain remaniement graphique ne doit pas emporter :
    la mention légale qui engage l'acheteur, et une issue quand le devis échoue.
    """

    def test_le_bouton_porte_la_mention_d_obligation_de_paiement(self, client, livre):
        """
        Art. L221-14 du code de la consommation : la fonction qui conclut la
        commande doit porter « commande avec obligation de paiement » ou une
        formule équivalente dénuée d'ambiguïté. Sous « Suivant », le
        consommateur n'était pas engagé — alors même que ce bouton réserve le
        stock et vide le panier.
        """
        client.post(reverse("commerce:panier_ajouter", args=[livre.pk]), {"quantite": 1})

        contenu = client.get(reverse("commerce:commander")).content.decode()

        bouton = contenu[contenu.index('id="bouton-commande"') :]
        bouton = bouton[: bouton.index("</button>")]
        assert "obligation de paiement" in bouton.lower()
        assert "Suivant" not in bouton

    def test_un_devis_indisponible_propose_une_issue(self, client, livre):
        """
        Un bouton grisé sans alternative, c'est un acheteur qui abandonne et un
        institut qui n'en sait rien. La page doit proposer le retrait sur place
        et de quoi joindre le secrétariat.
        """
        TarifLivraison.objects.all().delete()
        client.post(reverse("commerce:panier_ajouter", args=[livre.pk]), {"quantite": 1})

        contenu = client.get(reverse("commerce:commander")).content.decode()

        alerte = contenu[contenu.index('id="alerte-livraison-formulaire"') :]
        alerte = alerte[: alerte.index("</div>")]
        assert "Retrait à l'institut" in alerte
        assert "mailto:" in alerte
