"""
Table de vérité du contrôle d'accès — ADR-002.

Ce fichier est la contrepartie exécutable de la spécification : chaque ligne de
la table d'ordre y a son cas, plus les combinaisons qui comptent.
"""

from datetime import timedelta

import pytest
from django.contrib.auth.models import AnonymousUser
from django.utils import timezone

from apps.elearning.models import InscriptionModule, JournalAccesVideo, ModuleFormation
from apps.elearning.services.acces import (
    adresses_distinctes_recentes,
    journaliser_acces,
    liberer_flux,
    prerequis_satisfaits,
    verifier_acces,
)

R = JournalAccesVideo.Resultat


@pytest.fixture(autouse=True)
def _cache_propre():
    """Le quota s'appuie sur le cache : on repart d'un état neuf à chaque test."""
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()


# ──────────────────────────────────────────────
# Ligne 1 — le module doit être publié
# ──────────────────────────────────────────────


@pytest.mark.django_db
class TestModulePublie:
    def test_module_en_brouillon_refuse(self, lecon, module, utilisateur_etudiant, acces):
        module.statut = ModuleFormation.StatutPublication.BROUILLON
        module.save(update_fields=["statut"])
        decision = verifier_acces(utilisateur_etudiant, lecon)
        assert decision.autorise is False
        assert decision.motif == R.REFUSE_DROIT

    def test_module_archive_refuse(self, lecon, module, utilisateur_etudiant, acces):
        module.statut = ModuleFormation.StatutPublication.ARCHIVE
        module.save(update_fields=["statut"])
        assert verifier_acces(utilisateur_etudiant, lecon).autorise is False

    def test_le_responsable_voit_son_brouillon(self, lecon, module, enseignant):
        module.statut = ModuleFormation.StatutPublication.BROUILLON
        module.save(update_fields=["statut"])
        assert verifier_acces(enseignant.user, lecon).autorise is True

    def test_un_anonyme_ne_voit_pas_un_brouillon(self, lecon, module):
        """Même une leçon d'aperçu reste invisible tant que le module n'est pas publié."""
        module.statut = ModuleFormation.StatutPublication.BROUILLON
        module.save(update_fields=["statut"])
        decision = verifier_acces(AnonymousUser(), lecon)
        assert decision.autorise is False
        assert decision.motif == R.REFUSE_DROIT


# ──────────────────────────────────────────────
# Ligne 2 — l'aperçu gratuit est ouvert
# ──────────────────────────────────────────────


@pytest.mark.django_db
class TestApercuGratuit:
    def test_un_visiteur_anonyme_accede_a_l_apercu(self, lecon_apercu):
        assert verifier_acces(AnonymousUser(), lecon_apercu).autorise is True

    def test_l_apercu_reste_ouvert_sans_aucun_droit(self, lecon_apercu, utilisateur_etudiant):
        assert verifier_acces(utilisateur_etudiant, lecon_apercu).autorise is True


# ──────────────────────────────────────────────
# Ligne 3 — politique publique
# ──────────────────────────────────────────────


@pytest.mark.django_db
class TestPolitiquePublique:
    def test_module_public_ouvert_a_tous(self, lecon, module):
        module.politique_acces = ModuleFormation.PolitiqueAcces.PUBLIC
        module.save(update_fields=["politique_acces"])
        assert verifier_acces(AnonymousUser(), lecon).autorise is True


# ──────────────────────────────────────────────
# Ligne 4 — au-delà, il faut être connecté
# ──────────────────────────────────────────────


@pytest.mark.django_db
class TestAuthentification:
    def test_anonyme_refuse_sur_module_protege(self, lecon):
        decision = verifier_acces(AnonymousUser(), lecon)
        assert decision.autorise is False
        assert decision.motif == R.REFUSE_DROIT

    def test_utilisateur_absent_refuse(self, lecon):
        assert verifier_acces(None, lecon).autorise is False


# ──────────────────────────────────────────────
# Ligne 5 — gestionnaires
# ──────────────────────────────────────────────


@pytest.mark.django_db
class TestGestionnaires:
    def test_le_secretariat_accede_sans_droit_explicite(self, lecon, secretaire):
        assert verifier_acces(secretaire, lecon).autorise is True

    def test_un_superutilisateur_accede(self, lecon, admin_user):
        assert verifier_acces(admin_user, lecon).autorise is True

    def test_l_enseignant_responsable_accede(self, lecon, enseignant):
        assert verifier_acces(enseignant.user, lecon).autorise is True

    def test_un_enseignant_non_responsable_est_refuse(self, lecon, db):
        from apps.accounts.models import User
        from apps.formations.models import Professeur

        autre_utilisateur = User.objects.create_user(
            username="autreprof", email="autreprof@iteag.org", password="motdepasse-long-12", role=User.Role.ENSEIGNANT
        )
        Professeur.objects.create(user=autre_utilisateur, nom="Labeth", prenom="Ruth", slug="ruth-labeth")
        assert verifier_acces(autre_utilisateur, lecon).autorise is False


# ──────────────────────────────────────────────
# Ligne 6 — politique « tout compte connecté »
# ──────────────────────────────────────────────


@pytest.mark.django_db
class TestPolitiqueAuthentifie:
    def test_tout_compte_connecte_accede(self, lecon, module, utilisateur_etudiant):
        module.politique_acces = ModuleFormation.PolitiqueAcces.AUTHENTIFIE
        module.save(update_fields=["politique_acces"])
        assert verifier_acces(utilisateur_etudiant, lecon).autorise is True

    def test_mais_pas_un_anonyme(self, lecon, module):
        module.politique_acces = ModuleFormation.PolitiqueAcces.AUTHENTIFIE
        module.save(update_fields=["politique_acces"])
        assert verifier_acces(AnonymousUser(), lecon).autorise is False


# ──────────────────────────────────────────────
# Ligne 7 — un profil étudiant est nécessaire
# ──────────────────────────────────────────────


@pytest.mark.django_db
class TestProfilEtudiant:
    def test_compte_sans_profil_etudiant_refuse(self, lecon, db):
        from apps.accounts.models import User

        simple = User.objects.create_user(
            username="sansprofil", email="sansprofil@iteag.org", password="motdepasse-long-12"
        )
        decision = verifier_acces(simple, lecon)
        assert decision.autorise is False
        assert decision.motif == R.REFUSE_DROIT


# ──────────────────────────────────────────────
# Ligne 8 — un droit doit exister
# ──────────────────────────────────────────────


@pytest.mark.django_db
class TestExistenceDuDroit:
    def test_etudiant_sans_acces_refuse(self, lecon, utilisateur_etudiant, profil):
        decision = verifier_acces(utilisateur_etudiant, lecon)
        assert decision.autorise is False
        assert decision.motif == R.REFUSE_DROIT

    def test_etudiant_avec_acces_autorise(self, lecon, utilisateur_etudiant, acces):
        decision = verifier_acces(utilisateur_etudiant, lecon)
        assert decision.autorise is True
        assert decision.inscription == acces

    def test_l_acces_d_un_autre_ne_profite_pas(self, lecon, module, utilisateur_etudiant, profil, db):
        from apps.academics.models import ProfilEtudiant
        from apps.accounts.models import User
        from apps.elearning.services.octroi import octroyer

        autre_utilisateur = User.objects.create_user(
            username="paul", email="paul@iteag.org", password="motdepasse-long-12", role=User.Role.ETUDIANT
        )
        autre_profil = ProfilEtudiant.objects.create(
            utilisateur=autre_utilisateur,
            parcours=profil.parcours,
            promotion=profil.promotion,
            numero_etudiant="ETU-2024-002",
        )
        octroyer(autre_profil, module, notifier_etudiant=False)
        assert verifier_acces(utilisateur_etudiant, lecon).autorise is False


# ──────────────────────────────────────────────
# Ligne 9 — statut et fenêtre de validité
# ──────────────────────────────────────────────


@pytest.mark.django_db
class TestValiditeDuDroit:
    @pytest.mark.parametrize(
        "statut",
        [
            InscriptionModule.StatutAcces.SUSPENDU,
            InscriptionModule.StatutAcces.EXPIRE,
            InscriptionModule.StatutAcces.REVOQUE,
        ],
    )
    def test_statut_bloquant_refuse(self, lecon, utilisateur_etudiant, acces, statut):
        acces.statut = statut
        acces.save(update_fields=["statut"])
        decision = verifier_acces(utilisateur_etudiant, lecon)
        assert decision.autorise is False
        assert decision.motif == R.REFUSE_EXPIRE

    def test_termine_autorise_la_revision_si_le_module_le_permet(self, lecon, module, utilisateur_etudiant, acces):
        acces.statut = InscriptionModule.StatutAcces.TERMINE
        acces.save(update_fields=["statut"])
        assert module.autorise_revision is True
        assert verifier_acces(utilisateur_etudiant, lecon).autorise is True

    def test_termine_refuse_si_la_revision_est_fermee(self, lecon, module, utilisateur_etudiant, acces):
        module.autorise_revision = False
        module.save(update_fields=["autorise_revision"])
        acces.statut = InscriptionModule.StatutAcces.TERMINE
        acces.save(update_fields=["statut"])
        assert verifier_acces(utilisateur_etudiant, lecon).autorise is False

    def test_acces_pas_encore_ouvert_refuse(self, lecon, utilisateur_etudiant, acces):
        acces.date_debut_acces = timezone.localdate() + timedelta(days=7)
        acces.save(update_fields=["date_debut_acces"])
        assert verifier_acces(utilisateur_etudiant, lecon).motif == R.REFUSE_EXPIRE

    def test_acces_echu_refuse(self, lecon, utilisateur_etudiant, acces):
        acces.date_debut_acces = timezone.localdate() - timedelta(days=30)
        acces.date_fin_acces = timezone.localdate() - timedelta(days=1)
        acces.save(update_fields=["date_debut_acces", "date_fin_acces"])
        assert verifier_acces(utilisateur_etudiant, lecon).motif == R.REFUSE_EXPIRE

    def test_dernier_jour_encore_valable(self, lecon, utilisateur_etudiant, acces):
        acces.date_fin_acces = timezone.localdate()
        acces.save(update_fields=["date_fin_acces"])
        assert verifier_acces(utilisateur_etudiant, lecon).autorise is True


# ──────────────────────────────────────────────
# Ligne 10 — prérequis
# ──────────────────────────────────────────────


@pytest.mark.django_db
class TestPrerequis:
    @pytest.fixture
    def module_prealable(self, db, discipline):
        return ModuleFormation.objects.create(
            titre="Introduction à la théologie",
            slug="introduction-theologie",
            discipline=discipline,
            statut=ModuleFormation.StatutPublication.PUBLIE,
        )

    def test_prerequis_non_termine_refuse(self, lecon, module, module_prealable, utilisateur_etudiant, acces, profil):
        from apps.elearning.services.octroi import octroyer

        module.prerequis.add(module_prealable)
        octroyer(profil, module_prealable, notifier_etudiant=False)
        decision = verifier_acces(utilisateur_etudiant, lecon)
        assert decision.autorise is False
        assert decision.motif == R.REFUSE_PREREQUIS

    def test_prerequis_termine_autorise(self, lecon, module, module_prealable, utilisateur_etudiant, acces, profil):
        from apps.elearning.services.octroi import octroyer

        module.prerequis.add(module_prealable)
        prealable = octroyer(profil, module_prealable, notifier_etudiant=False)
        prealable.statut = InscriptionModule.StatutAcces.TERMINE
        prealable.save(update_fields=["statut"])
        assert verifier_acces(utilisateur_etudiant, lecon).autorise is True

    def test_sans_prerequis_la_condition_est_satisfaite(self, module, profil):
        assert prerequis_satisfaits(profil, module) is True

    def test_tous_les_prerequis_comptent(self, module, module_prealable, profil, discipline, db):
        second = ModuleFormation.objects.create(
            titre="Herméneutique",
            slug="hermeneutique",
            discipline=discipline,
            statut=ModuleFormation.StatutPublication.PUBLIE,
        )
        module.prerequis.add(module_prealable, second)
        from apps.elearning.services.octroi import octroyer

        premier = octroyer(profil, module_prealable, notifier_etudiant=False)
        premier.statut = InscriptionModule.StatutAcces.TERMINE
        premier.save(update_fields=["statut"])
        assert prerequis_satisfaits(profil, module) is False


# ──────────────────────────────────────────────
# Ligne 11 — quota de lectures simultanées
# ──────────────────────────────────────────────


@pytest.mark.django_db
class TestQuotaDeFlux:
    def test_une_seconde_lecture_ailleurs_est_refusee(self, lecon, utilisateur_etudiant, acces):
        premier = verifier_acces(utilisateur_etudiant, lecon, verifier_quota=True, identifiant_flux="appareil-1")
        assert premier.autorise is True

        second = verifier_acces(utilisateur_etudiant, lecon, verifier_quota=True, identifiant_flux="appareil-2")
        assert second.autorise is False
        assert second.motif == R.REFUSE_QUOTA

    def test_reactualiser_sa_propre_lecture_reste_possible(self, lecon, utilisateur_etudiant, acces):
        verifier_acces(utilisateur_etudiant, lecon, verifier_quota=True, identifiant_flux="appareil-1")
        encore = verifier_acces(utilisateur_etudiant, lecon, verifier_quota=True, identifiant_flux="appareil-1")
        assert encore.autorise is True

    def test_liberer_le_flux_rouvre_la_lecture(self, lecon, utilisateur_etudiant, acces):
        verifier_acces(utilisateur_etudiant, lecon, verifier_quota=True, identifiant_flux="appareil-1")
        liberer_flux(utilisateur_etudiant)
        assert (
            verifier_acces(utilisateur_etudiant, lecon, verifier_quota=True, identifiant_flux="appareil-2").autorise
            is True
        )

    def test_le_quota_n_est_pas_verifie_a_l_affichage(self, lecon, utilisateur_etudiant, acces):
        """Consulter la page ne consomme pas de flux."""
        verifier_acces(utilisateur_etudiant, lecon, verifier_quota=True, identifiant_flux="appareil-1")
        assert verifier_acces(utilisateur_etudiant, lecon).autorise is True

    def test_quota_desactivable(self, lecon, utilisateur_etudiant, acces, settings):
        settings.ELEARNING_FLUX_SIMULTANES_MAX = 0
        verifier_acces(utilisateur_etudiant, lecon, verifier_quota=True, identifiant_flux="a")
        assert verifier_acces(utilisateur_etudiant, lecon, verifier_quota=True, identifiant_flux="b").autorise is True


# ──────────────────────────────────────────────
# Ordre de la table : le premier refus l'emporte
# ──────────────────────────────────────────────


@pytest.mark.django_db
class TestOrdreDesRefus:
    def test_un_module_non_publie_prime_sur_le_droit(self, lecon, module, utilisateur_etudiant, acces):
        """Même avec un accès valide, un brouillon reste invisible."""
        module.statut = ModuleFormation.StatutPublication.BROUILLON
        module.save(update_fields=["statut"])
        assert verifier_acces(utilisateur_etudiant, lecon).motif == R.REFUSE_DROIT

    def test_l_expiration_prime_sur_les_prerequis(self, lecon, module, utilisateur_etudiant, acces, profil, discipline):
        prealable = ModuleFormation.objects.create(
            titre="Préalable",
            slug="prealable",
            discipline=discipline,
            statut=ModuleFormation.StatutPublication.PUBLIE,
        )
        module.prerequis.add(prealable)
        acces.statut = InscriptionModule.StatutAcces.REVOQUE
        acces.save(update_fields=["statut"])
        assert verifier_acces(utilisateur_etudiant, lecon).motif == R.REFUSE_EXPIRE


# ──────────────────────────────────────────────
# Messages et traçabilité
# ──────────────────────────────────────────────


@pytest.mark.django_db
class TestMessagesEtJournal:
    def test_chaque_refus_porte_un_message_utile(self, lecon, utilisateur_etudiant, profil):
        decision = verifier_acces(utilisateur_etudiant, lecon)
        assert decision.message
        assert "secrétariat" in decision.message.lower()

    def test_les_messages_different_selon_le_motif(self, lecon, utilisateur_etudiant, acces):
        sans_droit = verifier_acces(AnonymousUser(), lecon)
        acces.statut = InscriptionModule.StatutAcces.EXPIRE
        acces.save(update_fields=["statut"])
        expire = verifier_acces(utilisateur_etudiant, lecon)
        assert sans_droit.message != expire.message

    def test_un_acces_autorise_est_journalise(self, lecon, utilisateur_etudiant, acces, request_factory):
        requete = request_factory.get("/", REMOTE_ADDR="198.51.100.7", HTTP_USER_AGENT="Navigateur")
        decision = verifier_acces(utilisateur_etudiant, lecon)
        entree = journaliser_acces(decision, utilisateur=utilisateur_etudiant, lecon=lecon, request=requete, ttl=300)
        assert entree.resultat == R.AUTORISE
        assert entree.adresse_ip == "198.51.100.7"
        assert entree.ttl_accorde == 300
        # L'empreinte du navigateur est stockée hachée, pas en clair.
        assert entree.user_agent_hash and "Navigateur" not in entree.user_agent_hash

    def test_un_refus_est_journalise_avec_son_motif(self, lecon, utilisateur_etudiant, profil, request_factory):
        decision = verifier_acces(utilisateur_etudiant, lecon)
        entree = journaliser_acces(
            decision, utilisateur=utilisateur_etudiant, lecon=lecon, request=request_factory.get("/")
        )
        assert entree.resultat == R.REFUSE_DROIT

    def test_detection_de_partage_par_adresses_distinctes(self, lecon, utilisateur_etudiant, acces, request_factory):
        decision = verifier_acces(utilisateur_etudiant, lecon)
        for adresse in ("198.51.100.1", "198.51.100.2", "203.0.113.9"):
            journaliser_acces(
                decision,
                utilisateur=utilisateur_etudiant,
                lecon=lecon,
                request=request_factory.get("/", REMOTE_ADDR=adresse),
            )
        assert adresses_distinctes_recentes(utilisateur_etudiant) == 3
