"""
La réparation planifiée — ce qui reste quand Stripe a cessé de redélivrer.

Un encaissement sans contrepartie est le seul défaut de ce système qui coûte
de l'argent à quelqu'un d'autre que l'ITEAG : l'étudiant a payé, et n'a rien.
Ces tests exigent deux choses de la tâche de rattrapage — qu'elle rattrape, et
qu'elle prévienne une personne quand elle n'y arrive pas. Sans la seconde, on
aurait remplacé un silence par un autre.
"""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.accounts.models import User
from apps.core.models import Notification
from apps.elearning.models import InscriptionModule
from apps.paiements.models import Reglement
from apps.paiements.services import attribution
from apps.paiements.tasks import reparer_livraisons


@pytest.fixture
def secretaire(db):
    return User.objects.create_user(
        username="secretariat_reparation",
        email="secretariat@iteag.org",
        password="motdepasse-long-12",
        role=User.Role.SECRETARIAT,
    )


def _payer_sans_delivrer(reglement, *, il_y_a_minutes=60):
    """Place le règlement dans l'état exact que la panne produit."""
    Reglement.objects.filter(pk=reglement.pk).update(
        statut=Reglement.Statut.PAYE,
        date_paiement=timezone.now() - timedelta(minutes=il_y_a_minutes),
        contrepartie_delivree=False,
    )
    reglement.refresh_from_db()
    return reglement


@pytest.mark.django_db
class TestLaReparationRattrape:
    def test_un_reglement_paye_non_delivre_est_rattrape(self, reglement, etudiant, module_vendu):
        _payer_sans_delivrer(reglement)

        assert reparer_livraisons() == 1

        reglement.refresh_from_db()
        assert reglement.contrepartie_delivree is True
        inscription = InscriptionModule.objects.get(etudiant=etudiant, module=module_vendu)
        assert inscription.statut == InscriptionModule.StatutAcces.ACTIF

    def test_un_reglement_trop_recent_est_laisse_tranquille(self, reglement, etudiant, module_vendu):
        """Une livraison est peut-être simplement en train de s'exécuter."""
        _payer_sans_delivrer(reglement, il_y_a_minutes=1)

        assert reparer_livraisons() == 0

        reglement.refresh_from_db()
        assert reglement.contrepartie_delivree is False

    def test_un_reglement_deja_delivre_n_est_pas_rejoue(self, reglement):
        _payer_sans_delivrer(reglement)
        attribution.delivrer(reglement)

        assert reparer_livraisons() == 0

    def test_un_reglement_non_paye_n_ouvre_rien(self, reglement, etudiant, module_vendu):
        assert reparer_livraisons() == 0
        assert InscriptionModule.objects.filter(etudiant=etudiant, module=module_vendu).exists() is False

    def test_un_rattrapage_reussi_remet_le_compteur_a_zero(self, monkeypatch, reglement):
        """Un règlement rattrapé au deuxième essai n'est plus un incident ouvert."""
        _payer_sans_delivrer(reglement)
        vrai_delivrer = attribution.delivrer
        monkeypatch.setattr(attribution, "delivrer", _delivrer_en_panne)
        reparer_livraisons()
        reglement.refresh_from_db()
        assert reglement.tentatives_livraison == 1

        monkeypatch.setattr(attribution, "delivrer", vrai_delivrer)
        reparer_livraisons()

        reglement.refresh_from_db()
        assert reglement.contrepartie_delivree is True
        assert reglement.tentatives_livraison == 0
        assert reglement.derniere_erreur_livraison == ""


def _delivrer_en_panne(reglement, **kwargs):
    raise RuntimeError("Le dossier étudiant a disparu entre-temps.")


@pytest.mark.django_db
class TestLaReparationQuiEchoueSeDit:
    def test_un_echec_isole_ne_derange_encore_personne(self, monkeypatch, reglement, secretaire):
        """Prévenir au premier échec ferait du bruit pour une panne d'une minute."""
        _payer_sans_delivrer(reglement)
        monkeypatch.setattr(attribution, "delivrer", _delivrer_en_panne)

        reparer_livraisons()

        reglement.refresh_from_db()
        assert reglement.tentatives_livraison == 1
        assert reglement.livraison_signalee is False
        assert Notification.objects.filter(destinataire=secretaire).exists() is False

    def test_deux_echecs_previennent_le_secretariat(self, monkeypatch, reglement, secretaire):
        """Le test qui compte : au bout de deux essais, quelqu'un l'apprend."""
        _payer_sans_delivrer(reglement)
        monkeypatch.setattr(attribution, "delivrer", _delivrer_en_panne)

        reparer_livraisons()
        reparer_livraisons()

        reglement.refresh_from_db()
        assert reglement.tentatives_livraison == 2
        assert reglement.livraison_signalee is True
        notification = Notification.objects.filter(destinataire=secretaire).get()
        assert "sans contrepartie" in notification.titre
        assert str(reglement.pk) in notification.message or str(reglement.pk) in notification.url_cible

    def test_l_alerte_ne_se_repete_pas_a_chaque_tournee(self, monkeypatch, reglement, secretaire):
        """Une alerte qui tombe tous les quarts d'heure finit par ne plus être lue."""
        _payer_sans_delivrer(reglement)
        monkeypatch.setattr(attribution, "delivrer", _delivrer_en_panne)

        for _ in range(5):
            reparer_livraisons()

        assert Notification.objects.filter(destinataire=secretaire).count() == 1

    def test_l_echec_est_consigne_pour_le_secretariat(self, monkeypatch, reglement, secretaire):
        _payer_sans_delivrer(reglement)
        monkeypatch.setattr(attribution, "delivrer", _delivrer_en_panne)

        reparer_livraisons()

        reglement.refresh_from_db()
        assert "dossier étudiant a disparu" in reglement.derniere_erreur_livraison

    def test_sans_destinataire_actif_le_signalement_reste_ouvert(self, monkeypatch, reglement):
        """Aucune personne à prévenir : l'incident ne doit pas être classé pour autant."""
        _payer_sans_delivrer(reglement)
        monkeypatch.setattr(attribution, "delivrer", _delivrer_en_panne)

        reparer_livraisons()
        reparer_livraisons()

        reglement.refresh_from_db()
        assert reglement.tentatives_livraison == 2
        assert reglement.livraison_signalee is False

    def test_un_echec_n_interrompt_pas_la_tournee(self, monkeypatch, reglement, module_vendu, etudiant):
        """Le premier règlement en panne ne doit pas priver le suivant de son rattrapage."""
        from decimal import Decimal

        _payer_sans_delivrer(reglement, il_y_a_minutes=120)
        second = Reglement.objects.create(
            nature=Reglement.Nature.MODULE,
            module=module_vendu,
            etudiant=etudiant,
            utilisateur=etudiant.utilisateur,
            email=etudiant.utilisateur.email,
            libelle="Second règlement",
            montant_ttc=Decimal("120.00"),
            taux_tva=Decimal("0.00"),
        )
        _payer_sans_delivrer(second, il_y_a_minutes=60)

        vrai_delivrer = attribution.delivrer

        def delivrer_sauf_le_premier(a_livrer, **kwargs):
            if a_livrer.pk == reglement.pk:
                raise RuntimeError("Panne sur le premier.")
            return vrai_delivrer(a_livrer, **kwargs)

        monkeypatch.setattr(attribution, "delivrer", delivrer_sauf_le_premier)

        assert reparer_livraisons() == 1

        second.refresh_from_db()
        assert second.contrepartie_delivree is True
