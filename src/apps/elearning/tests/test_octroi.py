"""Tests de l'octroi et du retrait des droits d'accès."""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.academics.models import ProfilEtudiant
from apps.core.models import JournalAudit, Notification
from apps.elearning.models import InscriptionModule, ModuleFormation, RegleAccesParcours
from apps.elearning.services.octroi import (
    expirer_acces_echus,
    octroyer,
    octroyer_modules_du_parcours,
    prolonger,
    propager_statut_etudiant,
    revoquer,
)


@pytest.mark.django_db
class TestOctroi:
    def test_ouvre_un_acces_actif(self, profil, module):
        inscription = octroyer(profil, module, notifier_etudiant=False)
        assert inscription.statut == InscriptionModule.StatutAcces.ACTIF
        assert inscription.est_active() is True

    def test_est_idempotent(self, profil, module):
        premier = octroyer(profil, module, notifier_etudiant=False)
        second = octroyer(profil, module, notifier_etudiant=False)
        assert premier.pk == second.pk
        assert InscriptionModule.objects.filter(etudiant=profil, module=module).count() == 1

    def test_pose_une_echeance_si_demandee(self, profil, module):
        inscription = octroyer(profil, module, duree_jours=30, notifier_etudiant=False)
        assert inscription.date_fin_acces == timezone.localdate() + timedelta(days=30)

    def test_sans_duree_l_acces_est_sans_terme(self, profil, module):
        assert octroyer(profil, module, notifier_etudiant=False).date_fin_acces is None

    def test_l_octroi_est_journalise(self, profil, module, secretaire):
        octroyer(profil, module, octroye_par=secretaire, notifier_etudiant=False)
        assert JournalAudit.objects.filter(action="octroi_acces", utilisateur=secretaire).exists()

    def test_l_etudiant_est_notifie(self, profil, module):
        octroyer(profil, module)
        assert Notification.objects.filter(
            destinataire=profil.utilisateur, type_notification=Notification.Type.ACCES_OCTROYE
        ).exists()

    def test_pas_de_notification_pour_un_module_non_publie(self, profil, module):
        module.statut = ModuleFormation.StatutPublication.BROUILLON
        module.save(update_fields=["statut"])
        octroyer(profil, module)
        assert Notification.objects.filter(destinataire=profil.utilisateur).count() == 0

    def test_un_acces_revoque_est_retabli_sans_perdre_la_progression(self, profil, module):
        inscription = octroyer(profil, module, notifier_etudiant=False)
        inscription.progression_percent = 40
        inscription.save(update_fields=["progression_percent"])
        revoquer(inscription, motif="Impayé")

        retabli = octroyer(profil, module, notifier_etudiant=False)
        assert retabli.pk == inscription.pk
        assert retabli.statut == InscriptionModule.StatutAcces.ACTIF
        assert retabli.progression_percent == 40
        assert retabli.motif_revocation == ""


@pytest.mark.django_db
class TestRevocationEtProlongation:
    def test_la_revocation_coupe_l_acces(self, acces):
        revoquer(acces, motif="Décision disciplinaire")
        acces.refresh_from_db()
        assert acces.statut == InscriptionModule.StatutAcces.REVOQUE
        assert acces.est_active() is False

    def test_la_revocation_est_journalisee_avec_son_motif(self, acces, secretaire):
        revoquer(acces, motif="Impayé", par=secretaire)
        entree = JournalAudit.objects.filter(action="revocation_acces").first()
        assert entree is not None
        assert entree.metadonnees["motif"] == "Impayé"

    def test_la_prolongation_repousse_l_echeance(self, profil, module):
        inscription = octroyer(profil, module, duree_jours=10, notifier_etudiant=False)
        ancienne = inscription.date_fin_acces
        prolonger(inscription, jours=30)
        inscription.refresh_from_db()
        assert inscription.date_fin_acces == ancienne + timedelta(days=30)

    def test_prolonger_un_acces_expire_le_reactive(self, acces):
        acces.date_debut_acces = timezone.localdate() - timedelta(days=30)
        acces.date_fin_acces = timezone.localdate() - timedelta(days=5)
        acces.statut = InscriptionModule.StatutAcces.EXPIRE
        acces.save(update_fields=["date_debut_acces", "date_fin_acces", "statut"])

        prolonger(acces, jours=30)
        acces.refresh_from_db()
        assert acces.statut == InscriptionModule.StatutAcces.ACTIF
        # L'échéance repart d'aujourd'hui, pas d'une date déjà passée.
        assert acces.date_fin_acces == timezone.localdate() + timedelta(days=30)


@pytest.mark.django_db
class TestOctroiParParcours:
    def test_ouvre_les_modules_obligatoires_du_parcours(self, profil, module, parcours, discipline):
        facultatif = ModuleFormation.objects.create(
            titre="Module facultatif",
            slug="facultatif",
            discipline=discipline,
            statut=ModuleFormation.StatutPublication.PUBLIE,
        )
        RegleAccesParcours.objects.create(parcours=parcours, module=module, obligatoire=True)
        RegleAccesParcours.objects.create(parcours=parcours, module=facultatif, obligatoire=False)

        inscriptions = octroyer_modules_du_parcours(profil)
        assert len(inscriptions) == 1
        assert inscriptions[0].module == module
        assert inscriptions[0].source == InscriptionModule.SourceAcces.PARCOURS

    def test_respecte_la_duree_d_acces_de_la_regle(self, profil, module, parcours):
        RegleAccesParcours.objects.create(parcours=parcours, module=module, obligatoire=True, duree_acces_jours=60)
        inscription = octroyer_modules_du_parcours(profil)[0]
        assert inscription.date_fin_acces == timezone.localdate() + timedelta(days=60)

    def test_sans_regle_rien_n_est_ouvert(self, profil):
        assert octroyer_modules_du_parcours(profil) == []


@pytest.mark.django_db
class TestPropagationDuStatutEtudiant:
    def test_suspendre_l_etudiant_coupe_ses_acces(self, profil, acces):
        """La coupure est immédiate : le signal la déclenche à l'enregistrement."""
        profil.statut_inscription = ProfilEtudiant.StatutInscription.SUSPENDU
        profil.save(update_fields=["statut_inscription"])

        acces.refresh_from_db()
        assert acces.statut == InscriptionModule.StatutAcces.SUSPENDU
        assert acces.est_active() is False

    def test_le_service_est_idempotent(self, profil, acces):
        """Rejouer la propagation ne change rien une fois l'effet acquis."""
        profil.statut_inscription = ProfilEtudiant.StatutInscription.SUSPENDU
        profil.save(update_fields=["statut_inscription"])
        assert propager_statut_etudiant(profil) == 0

    def test_reactiver_l_etudiant_releve_ses_acces(self, profil, acces):
        profil.statut_inscription = ProfilEtudiant.StatutInscription.SUSPENDU
        profil.save(update_fields=["statut_inscription"])
        profil.statut_inscription = ProfilEtudiant.StatutInscription.ACTIF
        profil.save(update_fields=["statut_inscription"])

        acces.refresh_from_db()
        assert acces.statut == InscriptionModule.StatutAcces.ACTIF

    def test_une_revocation_individuelle_survit_a_la_reactivation(self, profil, acces, module, discipline):
        """Rétablir un étudiant ne doit pas annuler une décision prise module par module."""
        autre = ModuleFormation.objects.create(
            titre="Autre",
            slug="autre",
            discipline=discipline,
            statut=ModuleFormation.StatutPublication.PUBLIE,
        )
        autre_acces = octroyer(profil, autre, notifier_etudiant=False)
        revoquer(autre_acces, motif="Cas particulier")

        profil.statut_inscription = ProfilEtudiant.StatutInscription.SUSPENDU
        profil.save(update_fields=["statut_inscription"])
        profil.statut_inscription = ProfilEtudiant.StatutInscription.ACTIF
        profil.save(update_fields=["statut_inscription"])

        acces.refresh_from_db()
        autre_acces.refresh_from_db()
        assert acces.statut == InscriptionModule.StatutAcces.ACTIF
        assert autre_acces.statut == InscriptionModule.StatutAcces.REVOQUE

    def test_un_etudiant_inactif_est_aussi_bloque(self, profil, acces):
        profil.statut_inscription = ProfilEtudiant.StatutInscription.INACTIF
        profil.save(update_fields=["statut_inscription"])
        acces.refresh_from_db()
        assert acces.statut == InscriptionModule.StatutAcces.SUSPENDU


@pytest.mark.django_db
class TestExpiration:
    def test_les_acces_echus_basculent_en_expire(self, acces):
        acces.date_debut_acces = timezone.localdate() - timedelta(days=30)
        acces.date_fin_acces = timezone.localdate() - timedelta(days=1)
        acces.save(update_fields=["date_debut_acces", "date_fin_acces"])

        assert expirer_acces_echus() == 1
        acces.refresh_from_db()
        assert acces.statut == InscriptionModule.StatutAcces.EXPIRE

    def test_un_acces_courant_n_est_pas_touche(self, acces):
        acces.date_fin_acces = timezone.localdate() + timedelta(days=10)
        acces.save(update_fields=["date_fin_acces"])
        assert expirer_acces_echus() == 0

    def test_un_acces_sans_terme_n_est_jamais_expire(self, acces):
        assert acces.date_fin_acces is None
        assert expirer_acces_echus() == 0

    def test_la_tache_celery_delegue_au_service(self, acces):
        from apps.elearning.tasks import expirer_acces

        acces.date_debut_acces = timezone.localdate() - timedelta(days=30)
        acces.date_fin_acces = timezone.localdate() - timedelta(days=1)
        acces.save(update_fields=["date_debut_acces", "date_fin_acces"])
        assert expirer_acces() == 1
