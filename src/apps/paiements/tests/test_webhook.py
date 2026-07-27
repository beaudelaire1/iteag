"""
Le webhook Stripe — là où l'argent devient un droit.

Ce fichier tient la promesse centrale du paiement en ligne : ce qui est payé
est délivré, une seule fois, et ce qui est remboursé est repris. Chaque test
correspond à une manière connue de perdre de l'argent ou d'en faire perdre.
"""

from decimal import Decimal

import pytest
from django.urls import reverse

from apps.elearning.models import InscriptionModule
from apps.paiements.models import EvenementStripe, Reglement
from apps.paiements.services import webhook
from apps.paiements.tests.conftest import evenement


def session_payee(reglement, montant=None):
    return {
        "id": reglement.session_stripe,
        "client_reference_id": str(reglement.pk),
        "payment_status": "paid",
        "payment_intent": "pi_test_123",
        "amount_total": montant if montant is not None else reglement.montant_en_centimes,
    }


# ══════════════════════════════════════════════
# Un paiement ouvre l'accès
# ══════════════════════════════════════════════


@pytest.mark.django_db
class TestUnPaiementOuvreLAcces:
    def test_le_reglement_passe_a_paye(self, reglement):
        webhook.traiter(evenement("checkout.session.completed", session_payee(reglement)))
        reglement.refresh_from_db()
        assert reglement.statut == Reglement.Statut.PAYE
        assert reglement.date_paiement is not None

    def test_l_acces_au_module_est_octroye(self, reglement, etudiant, module_vendu):
        webhook.traiter(evenement("checkout.session.completed", session_payee(reglement)))
        inscription = InscriptionModule.objects.get(etudiant=etudiant, module=module_vendu)
        assert inscription.statut == InscriptionModule.StatutAcces.ACTIF
        assert inscription.source == InscriptionModule.SourceAcces.ACHAT

    def test_l_acces_achete_est_perpetuel(self, reglement, etudiant, module_vendu):
        """Décision commerciale : ce qui est acheté ne s'éteint pas."""
        webhook.traiter(evenement("checkout.session.completed", session_payee(reglement)))
        inscription = InscriptionModule.objects.get(etudiant=etudiant, module=module_vendu)
        assert inscription.date_fin_acces is None
        assert inscription.est_active() is True

    def test_l_etudiant_peut_alors_lire_la_lecon(self, client, reglement, etudiant, module_vendu):
        """Le test qui compte pour l'étudiant : après avoir payé, ça s'ouvre."""
        lecon = module_vendu.lecons().first()
        adresse = reverse("elearning:lecon_playback", args=[module_vendu.slug, lecon.slug])
        client.force_login(etudiant.utilisateur)
        assert client.post(adresse).status_code == 403

        webhook.traiter(evenement("checkout.session.completed", session_payee(reglement)))
        assert client.post(adresse).status_code == 200


# ══════════════════════════════════════════════
# Une notification rejouée ne délivre pas deux fois
# ══════════════════════════════════════════════


@pytest.mark.django_db
class TestIdempotence:
    def test_la_meme_notification_deux_fois_est_refusee_la_seconde(self, reglement):
        """Stripe redélivre : c'est la règle, pas l'exception."""
        charge = evenement("checkout.session.completed", session_payee(reglement))
        webhook.traiter(charge)
        with pytest.raises(webhook.EvenementDejaTraite):
            webhook.traiter(charge)
        assert EvenementStripe.objects.filter(identifiant="evt_test_1").count() == 1

    def test_deux_notifications_distinctes_ne_delivrent_qu_une_fois(self, reglement, etudiant, module_vendu):
        """Deux identifiants différents pour un même encaissement : un seul accès."""
        webhook.traiter(evenement("checkout.session.completed", session_payee(reglement), identifiant="evt_a"))
        webhook.traiter(evenement("checkout.session.completed", session_payee(reglement), identifiant="evt_b"))
        assert InscriptionModule.objects.filter(etudiant=etudiant, module=module_vendu).count() == 1

    def test_la_contrepartie_est_marquee_delivree(self, reglement):
        webhook.traiter(evenement("checkout.session.completed", session_payee(reglement)))
        reglement.refresh_from_db()
        assert reglement.contrepartie_delivree is True


# ══════════════════════════════════════════════
# Ce qui ne doit jamais ouvrir un accès
# ══════════════════════════════════════════════


@pytest.mark.django_db
class TestCeQuiNOuvrePas:
    def test_un_montant_encaisse_different_est_refuse(self, reglement, etudiant, module_vendu):
        """
        Le scénario coûteux : délivrer une formation à 120 € sur 3 € encaissés.
        Le traitement doit lever, pour que Stripe redélivre et que l'écart se
        voie dans le journal plutôt que de passer inaperçu.
        """
        with pytest.raises(ValueError, match="Montant encaissé"):
            webhook.traiter(evenement("checkout.session.completed", session_payee(reglement, montant=300)))
        assert InscriptionModule.objects.filter(etudiant=etudiant, module=module_vendu).exists() is False

    def test_une_session_impayee_n_ouvre_rien(self, reglement, etudiant, module_vendu):
        objet = session_payee(reglement) | {"payment_status": "unpaid"}
        webhook.traiter(evenement("checkout.session.completed", objet))
        reglement.refresh_from_db()
        assert reglement.statut == Reglement.Statut.EN_ATTENTE
        assert InscriptionModule.objects.filter(etudiant=etudiant, module=module_vendu).exists() is False

    def test_un_evenement_inconnu_est_ignore(self, reglement):
        assert webhook.traiter(evenement("invoice.created", {})) is None
        assert EvenementStripe.objects.count() == 0

    def test_une_session_expiree_n_ouvre_rien(self, reglement, etudiant, module_vendu):
        webhook.traiter(evenement("checkout.session.expired", {"client_reference_id": str(reglement.pk)}))
        reglement.refresh_from_db()
        assert reglement.statut == Reglement.Statut.ABANDONNE
        assert InscriptionModule.objects.filter(etudiant=etudiant, module=module_vendu).exists() is False


# ══════════════════════════════════════════════
# Un remboursement referme l'accès
# ══════════════════════════════════════════════


@pytest.mark.django_db
class TestUnRemboursementReferme:
    def _payer(self, reglement):
        webhook.traiter(evenement("checkout.session.completed", session_payee(reglement), identifiant="evt_paie"))

    def test_le_remboursement_revoque_l_acces(self, reglement, etudiant, module_vendu):
        """Sans cela, l'argent repart et la formation reste."""
        self._payer(reglement)
        webhook.traiter(
            evenement(
                "charge.refunded",
                {"payment_intent": "pi_test_123", "refunded": True},
                identifiant="evt_remb",
            )
        )
        reglement.refresh_from_db()
        assert reglement.statut == Reglement.Statut.REMBOURSE
        inscription = InscriptionModule.objects.get(etudiant=etudiant, module=module_vendu)
        assert inscription.statut == InscriptionModule.StatutAcces.REVOQUE

    def test_apres_remboursement_la_lecture_est_refusee(self, client, reglement, etudiant, module_vendu):
        self._payer(reglement)
        lecon = module_vendu.lecons().first()
        adresse = reverse("elearning:lecon_playback", args=[module_vendu.slug, lecon.slug])
        client.force_login(etudiant.utilisateur)
        assert client.post(adresse).status_code == 200

        webhook.traiter(
            evenement(
                "charge.refunded",
                {"payment_intent": "pi_test_123", "refunded": True},
                identifiant="evt_remb",
            )
        )
        assert client.post(adresse).status_code == 403

    def test_un_remboursement_partiel_ne_referme_rien(self, reglement, etudiant, module_vendu):
        """Rembourser un geste commercial ne retire pas la formation."""
        self._payer(reglement)
        webhook.traiter(
            evenement(
                "charge.refunded",
                {"payment_intent": "pi_test_123", "refunded": False},
                identifiant="evt_partiel",
            )
        )
        reglement.refresh_from_db()
        assert reglement.statut == Reglement.Statut.PAYE
        inscription = InscriptionModule.objects.get(etudiant=etudiant, module=module_vendu)
        assert inscription.statut == InscriptionModule.StatutAcces.ACTIF

    def test_une_contestation_bancaire_referme_sans_attendre(self, reglement, etudiant, module_vendu):
        """Rouvrir coûte un clic ; laisser consommer coûte la formation."""
        self._payer(reglement)
        webhook.traiter(
            evenement("charge.dispute.created", {"payment_intent": "pi_test_123"}, identifiant="evt_litige")
        )
        reglement.refresh_from_db()
        assert reglement.statut == Reglement.Statut.LITIGE
        inscription = InscriptionModule.objects.get(etudiant=etudiant, module=module_vendu)
        assert inscription.statut == InscriptionModule.StatutAcces.REVOQUE


# ══════════════════════════════════════════════
# La TVA saisie au formulaire
# ══════════════════════════════════════════════


@pytest.mark.django_db
class TestRepartitionDeLaTva:
    def test_sans_tva_tout_est_en_ht(self, reglement):
        assert reglement.montant_ht == Decimal("120.00")
        assert reglement.montant_tva == Decimal("0.00")

    def test_avec_tva_le_ht_et_la_tva_redonnent_le_ttc(self, module_vendu, etudiant):
        """Le contrôle qui compte pour la comptabilité : aucune dérive au centime."""
        regle = Reglement.objects.create(
            nature=Reglement.Nature.MODULE,
            module=module_vendu,
            etudiant=etudiant,
            email="a@b.fr",
            libelle="Avec TVA",
            montant_ttc=Decimal("120.00"),
            taux_tva=Decimal("20.00"),
        )
        assert regle.montant_ht == Decimal("100.00")
        assert regle.montant_tva == Decimal("20.00")
        assert regle.montant_ht + regle.montant_tva == regle.montant_ttc

    def test_un_montant_qui_ne_tombe_pas_juste_reste_exact(self, module_vendu, etudiant):
        regle = Reglement.objects.create(
            nature=Reglement.Nature.MODULE,
            module=module_vendu,
            etudiant=etudiant,
            email="a@b.fr",
            libelle="Arrondi",
            montant_ttc=Decimal("99.99"),
            taux_tva=Decimal("8.50"),
        )
        assert regle.montant_ht + regle.montant_tva == Decimal("99.99")

    def test_stripe_recoit_des_centimes_entiers(self, reglement):
        assert reglement.montant_en_centimes == 12000
