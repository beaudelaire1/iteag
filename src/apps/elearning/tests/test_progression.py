"""
Tests du suivi de progression.

L'enjeu n'est pas de compter des pourcentages : c'est de garantir qu'une
attestation ne peut pas s'obtenir sans avoir réellement visionné.
"""

import pytest

from apps.elearning.models import AttestationModule, InscriptionModule, ProgressionLecon
from apps.elearning.services.progression import (
    INCREMENT_MAX_SECONDES,
    enregistrer_progression,
    lecon_suivante,
    recalculer_progression_module,
)


@pytest.mark.django_db
class TestEnregistrementDeProgression:
    def test_premier_signal_cree_la_progression(self, acces, lecon):
        avancement = enregistrer_progression(acces, lecon, position_secondes=15, delta_secondes=15)
        assert avancement.pk is not None
        assert avancement.position_secondes == 15
        assert avancement.temps_visionnage_cumule == 15

    def test_les_signaux_s_accumulent(self, acces, lecon):
        for seconde in range(15, 61, 15):
            enregistrer_progression(acces, lecon, position_secondes=seconde, delta_secondes=15)
        avancement = ProgressionLecon.objects.get(inscription=acces, lecon=lecon)
        assert avancement.temps_visionnage_cumule == 60

    def test_le_pourcentage_suit_le_temps_reellement_vu(self, acces, lecon):
        # 300 s vues sur 600 s de leçon
        for _ in range(20):
            enregistrer_progression(acces, lecon, position_secondes=300, delta_secondes=15)
        assert ProgressionLecon.objects.get(inscription=acces, lecon=lecon).pourcentage_vu == 50

    def test_la_position_de_reprise_est_conservee(self, acces, lecon):
        enregistrer_progression(acces, lecon, position_secondes=247, delta_secondes=15)
        assert ProgressionLecon.objects.get(inscription=acces, lecon=lecon).position_secondes == 247


@pytest.mark.django_db
class TestResistanceALaFalsification:
    def test_un_increment_exagere_est_plafonne(self, acces, lecon):
        """Annoncer dix minutes d'un coup ne crédite que l'intervalle admis."""
        avancement = enregistrer_progression(acces, lecon, position_secondes=600, delta_secondes=600)
        assert avancement.temps_visionnage_cumule == INCREMENT_MAX_SECONDES

    def test_sauter_a_la_fin_ne_termine_pas_la_lecon(self, acces, lecon):
        avancement = enregistrer_progression(acces, lecon, position_secondes=600, delta_secondes=1)
        assert avancement.termine is False
        assert avancement.pourcentage_vu < 80

    def test_le_cumul_ne_depasse_pas_la_duree(self, acces, lecon):
        """Repasser la vidéo en boucle ne gonfle pas le temps vu."""
        for _ in range(100):
            enregistrer_progression(acces, lecon, position_secondes=600, delta_secondes=30)
        avancement = ProgressionLecon.objects.get(inscription=acces, lecon=lecon)
        assert avancement.temps_visionnage_cumule == lecon.duree_secondes
        assert avancement.pourcentage_vu == 100

    def test_un_delta_negatif_est_ignore(self, acces, lecon):
        enregistrer_progression(acces, lecon, position_secondes=100, delta_secondes=15)
        avancement = enregistrer_progression(acces, lecon, position_secondes=100, delta_secondes=-500)
        assert avancement.temps_visionnage_cumule == 15

    def test_une_position_hors_bornes_est_ramenee_a_la_duree(self, acces, lecon):
        avancement = enregistrer_progression(acces, lecon, position_secondes=999999, delta_secondes=15)
        assert avancement.position_secondes == lecon.duree_secondes


@pytest.mark.django_db
class TestCompletion:
    def _visionner_entierement(self, acces, lecon):
        signaux = lecon.duree_secondes // INCREMENT_MAX_SECONDES + 1
        for i in range(signaux):
            enregistrer_progression(
                acces,
                lecon,
                position_secondes=min((i + 1) * INCREMENT_MAX_SECONDES, lecon.duree_secondes),
                delta_secondes=INCREMENT_MAX_SECONDES,
            )

    def test_un_visionnage_complet_termine_la_lecon(self, acces, lecon):
        self._visionner_entierement(acces, lecon)
        avancement = ProgressionLecon.objects.get(inscription=acces, lecon=lecon)
        assert avancement.termine is True
        assert avancement.date_completion is not None

    def test_le_module_passe_a_termine(self, acces, lecon):
        self._visionner_entierement(acces, lecon)
        acces.refresh_from_db()
        assert acces.progression_percent == 100
        assert acces.statut == InscriptionModule.StatutAcces.TERMINE
        assert acces.date_completion is not None

    def test_les_lecons_facultatives_ne_comptent_pas(self, acces, lecon, lecon_apercu):
        """L'aperçu n'est pas obligatoire : il ne pèse pas dans la complétion."""
        self._visionner_entierement(acces, lecon)
        acces.refresh_from_db()
        assert acces.progression_percent == 100

    def test_progression_partielle_sur_deux_lecons(self, acces, lecon, chapitre, video_prete, db):
        from apps.elearning.models import Lecon

        seconde = Lecon.objects.create(
            chapitre=chapitre,
            titre="Seconde leçon",
            slug="seconde-lecon",
            video=video_prete,
            ordre=3,
            duree_secondes=600,
        )
        self._visionner_entierement(acces, lecon)
        acces.refresh_from_db()
        assert acces.progression_percent == 50
        assert acces.statut == InscriptionModule.StatutAcces.ACTIF
        assert seconde.pk is not None

    def test_module_sans_lecon_obligatoire_ne_plante_pas(self, acces, lecon_apercu, lecon):
        lecon.obligatoire = False
        lecon.save(update_fields=["obligatoire"])
        assert recalculer_progression_module(acces) == acces.progression_percent


@pytest.mark.django_db
class TestAttestation:
    def test_un_module_certifiant_emet_une_attestation(self, acces, lecon, module):
        module.certifiant = True
        module.save(update_fields=["certifiant"])

        for i in range(lecon.duree_secondes // INCREMENT_MAX_SECONDES + 1):
            enregistrer_progression(
                acces, lecon, position_secondes=min((i + 1) * 30, 600), delta_secondes=INCREMENT_MAX_SECONDES
            )

        attestation = AttestationModule.objects.filter(inscription=acces).first()
        assert attestation is not None
        assert attestation.numero.startswith("ITEAG-MOD-")
        assert attestation.code_verification

    def test_un_module_non_certifiant_n_en_emet_pas(self, acces, lecon, module):
        assert module.certifiant is False
        for _ in range(25):
            enregistrer_progression(acces, lecon, position_secondes=600, delta_secondes=30)
        assert AttestationModule.objects.filter(inscription=acces).count() == 0

    def test_l_attestation_n_est_pas_dupliquee(self, acces, lecon, module):
        module.certifiant = True
        module.save(update_fields=["certifiant"])
        for _ in range(40):
            enregistrer_progression(acces, lecon, position_secondes=600, delta_secondes=30)
        assert AttestationModule.objects.filter(inscription=acces).count() == 1

    def test_le_numero_est_sequentiel(self, acces, lecon, module, profil, discipline, db):
        from apps.elearning.models import ModuleFormation
        from apps.elearning.services.octroi import octroyer

        module.certifiant = True
        module.save(update_fields=["certifiant"])
        second_module = ModuleFormation.objects.create(
            titre="Second",
            slug="second",
            discipline=discipline,
            statut=ModuleFormation.StatutPublication.PUBLIE,
            certifiant=True,
        )
        second_acces = octroyer(profil, second_module, notifier_etudiant=False)

        from apps.elearning.services.progression import emettre_attestation

        acces.progression_percent = 100
        acces.save(update_fields=["progression_percent"])
        second_acces.progression_percent = 100
        second_acces.save(update_fields=["progression_percent"])

        premiere = emettre_attestation(acces)
        seconde = emettre_attestation(second_acces)
        assert premiere.numero != seconde.numero

    def test_pas_d_attestation_sous_le_seuil(self, acces, module):
        from apps.elearning.services.progression import emettre_attestation

        module.certifiant = True
        module.save(update_fields=["certifiant"])
        acces.progression_percent = 40
        acces.save(update_fields=["progression_percent"])
        assert emettre_attestation(acces) is None


@pytest.mark.django_db
class TestLeconSuivante:
    def test_propose_la_premiere_lecon_non_faite(self, acces, lecon, lecon_apercu):
        assert lecon_suivante(acces) == lecon

    def test_avance_apres_completion(self, acces, lecon, lecon_apercu):
        for _ in range(25):
            enregistrer_progression(acces, lecon, position_secondes=600, delta_secondes=30)
        assert lecon_suivante(acces) == lecon_apercu

    def test_retourne_rien_quand_tout_est_fait(self, acces, lecon):
        for _ in range(25):
            enregistrer_progression(acces, lecon, position_secondes=600, delta_secondes=30)
        assert lecon_suivante(acces) is None
