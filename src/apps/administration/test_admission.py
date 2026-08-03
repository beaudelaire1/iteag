"""Tests de l'orchestration admission → compte → accès aux modules."""

import re

import pytest
from django.core import mail
from django.core.management import call_command
from django.urls import reverse

from apps.academics.models import ProfilEtudiant, Promotion
from apps.accounts.models import User
from apps.administration.services.admission import accepter_dossier, numero_etudiant_suivant
from apps.admissions.models import DossierCandidature
from apps.elearning.models import InscriptionModule, ModuleFormation, RegleAccesParcours
from apps.formations.models import Parcours


@pytest.fixture
def parcours(db):
    return Parcours.objects.create(
        nom="Parcours diplômant",
        slug="parcours-diplomant",
        type_parcours=Parcours.TypeParcours.DIPLOMANT_ITEAG,
    )


@pytest.fixture
def promotion(db, parcours):
    return Promotion.objects.create(nom="Promotion 2026", parcours=parcours, annee_debut=2026, annee_fin=2032)


@pytest.fixture
def dossier(db, parcours):
    return DossierCandidature.objects.create(
        nom="Durand",
        prenom="Marie",
        email="marie.durand@exemple.org",
        telephone="0690000000",
        parcours_souhaite=parcours,
        motivations="Servir l'Église.",
        statut=DossierCandidature.Statut.EN_EXAMEN,
    )


@pytest.fixture
def module_obligatoire(db, parcours):
    module = ModuleFormation.objects.create(
        titre="Introduction",
        slug="introduction",
        statut=ModuleFormation.StatutPublication.PUBLIE,
    )
    RegleAccesParcours.objects.create(parcours=parcours, module=module, obligatoire=True, duree_acces_jours=365)
    return module


@pytest.mark.django_db
class TestAcceptationDeCandidature:
    def test_cree_le_compte_et_le_profil(self, dossier, promotion):
        profil = accepter_dossier(dossier, promotion=promotion)
        assert profil.utilisateur.email == "marie.durand@exemple.org"
        assert profil.utilisateur.role == User.Role.ETUDIANT
        assert profil.statut_inscription == ProfilEtudiant.StatutInscription.PRE_INSCRIT
        # Sans séparateur : le numéro se dicte et se recherche d'une traite.
        assert re.fullmatch(r"ETU\d{4}\d{3}", profil.numero_etudiant), profil.numero_etudiant

    def test_le_compte_n_a_pas_de_mot_de_passe_utilisable(self, dossier, promotion):
        """Aucun mot de passe ne transite : le candidat le définit lui-même."""
        profil = accepter_dossier(dossier, promotion=promotion)
        assert profil.utilisateur.has_usable_password() is False

    def test_ouvre_les_modules_obligatoires(self, dossier, promotion, module_obligatoire):
        profil = accepter_dossier(dossier, promotion=promotion)
        inscriptions = InscriptionModule.objects.filter(etudiant=profil)
        assert inscriptions.count() == 1
        assert inscriptions.first().module == module_obligatoire
        assert inscriptions.first().source == InscriptionModule.SourceAcces.PARCOURS

    def test_marque_le_dossier_accepte_et_le_relie_au_compte(self, dossier, promotion):
        profil = accepter_dossier(dossier, promotion=promotion)
        dossier.refresh_from_db()
        assert dossier.statut == DossierCandidature.Statut.ACCEPTE
        assert dossier.utilisateur_cree == profil.utilisateur

    def test_journalise_le_changement(self, dossier, promotion):
        accepter_dossier(dossier, promotion=promotion)
        assert dossier.historique.filter(nouveau_statut=DossierCandidature.Statut.ACCEPTE).exists()

    def test_envoie_le_courriel_de_bienvenue_avec_un_lien(self, dossier, promotion):
        accepter_dossier(dossier, promotion=promotion)
        assert len(mail.outbox) == 1
        assert "Bienvenue" in mail.outbox[0].subject
        assert "/mot-de-passe/confirmer/" in mail.outbox[0].body

    def test_est_idempotente(self, dossier, promotion):
        premier = accepter_dossier(dossier, promotion=promotion)
        second = accepter_dossier(dossier, promotion=promotion)
        assert premier.pk == second.pk
        assert User.objects.filter(email=dossier.email).count() == 1

    def test_les_numeros_etudiants_ne_se_repetent_pas(self, dossier, promotion, parcours):
        accepter_dossier(dossier, promotion=promotion)
        autre = DossierCandidature.objects.create(
            nom="Martin",
            prenom="Paul",
            email="paul@exemple.org",
            parcours_souhaite=parcours,
            motivations="…",
            statut=DossierCandidature.Statut.EN_EXAMEN,
        )
        second = accepter_dossier(autre, promotion=promotion)
        assert second.numero_etudiant != ProfilEtudiant.objects.first().numero_etudiant

    def test_les_homonymes_obtiennent_des_identifiants_distincts(self, dossier, promotion, parcours):
        accepter_dossier(dossier, promotion=promotion)
        homonyme = DossierCandidature.objects.create(
            nom="Durand",
            prenom="Marie",
            email="marie2@exemple.org",
            parcours_souhaite=parcours,
            motivations="…",
            statut=DossierCandidature.Statut.EN_EXAMEN,
        )
        profil = accepter_dossier(homonyme, promotion=promotion)
        assert profil.utilisateur.username != "marie.durand"

    def test_numerotation_repart_a_un_chaque_annee(self, db):
        assert numero_etudiant_suivant(2030) == "ETU2030001"

    def test_la_numerotation_suit_le_dernier_numero_de_l_annee(self, db, parcours, promotion):
        """Le rang se lit dans le numéro : sans tiret, il faut le retrouver autrement."""
        compte = User.objects.create_user(
            username="deja-la", email="deja@iteag.org", password="motdepasse-long-12", role=User.Role.ETUDIANT
        )
        ProfilEtudiant.objects.create(
            utilisateur=compte, parcours=parcours, promotion=promotion, numero_etudiant="ETU2030007"
        )
        assert numero_etudiant_suivant(2030) == "ETU2030008"


@pytest.mark.django_db
class TestVueAcceptation:
    @pytest.fixture
    def secretaire(self, db):
        return User.objects.create_user(
            username="sec",
            email="sec@iteag.org",
            password="motdepasse-long-12",
            role=User.Role.SECRETARIAT,
            is_staff=True,
        )

    def test_l_acceptation_sans_promotion_est_refusee(self, client, secretaire, dossier):
        client.force_login(secretaire)
        client.post(
            reverse("administration:candidature_detail", kwargs={"pk": dossier.pk}),
            {"statut": DossierCandidature.Statut.ACCEPTE},
        )
        dossier.refresh_from_db()
        assert dossier.statut == DossierCandidature.Statut.EN_EXAMEN
        assert dossier.utilisateur_cree is None

    def test_l_acceptation_avec_promotion_ouvre_tout(self, client, secretaire, dossier, promotion, module_obligatoire):
        client.force_login(secretaire)
        client.post(
            reverse("administration:candidature_detail", kwargs={"pk": dossier.pk}),
            {"statut": DossierCandidature.Statut.ACCEPTE, "promotion": promotion.pk},
        )
        dossier.refresh_from_db()
        assert dossier.statut == DossierCandidature.Statut.ACCEPTE
        profil = dossier.utilisateur_cree.profil_etudiant
        assert InscriptionModule.objects.filter(etudiant=profil).count() == 1

    def test_un_autre_statut_suit_le_chemin_habituel(self, client, secretaire, dossier):
        client.force_login(secretaire)
        client.post(
            reverse("administration:candidature_detail", kwargs={"pk": dossier.pk}),
            {"statut": DossierCandidature.Statut.INCOMPLET, "commentaire": "Pièce manquante"},
        )
        dossier.refresh_from_db()
        assert dossier.statut == DossierCandidature.Statut.INCOMPLET
        assert dossier.utilisateur_cree is None


def _dossier(parcours, prenom, nom, statut=DossierCandidature.Statut.EN_EXAMEN):
    return DossierCandidature.objects.create(
        nom=nom,
        prenom=prenom,
        email=f"{prenom}.{nom}@exemple.org".lower(),
        parcours_souhaite=parcours,
        motivations="Servir l'Église.",
        statut=statut,
    )


@pytest.mark.django_db
class TestAcceptationGroupee:
    """
    L'action groupée doit faire ce que fait la fiche, pas moins.

    Elle se contentait de changer le statut : les dossiers finissaient
    « acceptés » sans compte, et « accepté » étant terminal, plus rien ne
    permettait de les rattraper depuis l'interface.
    """

    @pytest.fixture
    def secretaire(self, db):
        return User.objects.create_user(
            username="sec-groupee",
            email="sec-groupee@iteag.org",
            password="motdepasse-long-12",
            role=User.Role.SECRETARIAT,
            is_staff=True,
        )

    def test_l_acceptation_groupee_cree_un_compte_par_dossier(self, client, secretaire, parcours, promotion):
        premier = _dossier(parcours, "Marie", "Durand")
        second = _dossier(parcours, "Paul", "Martin")
        client.force_login(secretaire)

        client.post(
            reverse("administration:candidatures_bulk_status"),
            {"selected": [premier.pk, second.pk], "bulk_statut": DossierCandidature.Statut.ACCEPTE},
        )

        for dossier in (premier, second):
            dossier.refresh_from_db()
            assert dossier.statut == DossierCandidature.Statut.ACCEPTE
            assert dossier.utilisateur_cree is not None
            assert dossier.utilisateur_cree.profil_etudiant.promotion == promotion

    def test_un_dossier_en_echec_ne_prive_pas_les_autres(self, client, secretaire, parcours, promotion):
        """Un dossier qu'aucune transition n'autorise ne doit pas bloquer la fournée."""
        bloque = _dossier(parcours, "Jean", "Soumis", statut=DossierCandidature.Statut.SOUMIS)
        valide = _dossier(parcours, "Anne", "Examen")
        client.force_login(secretaire)

        client.post(
            reverse("administration:candidatures_bulk_status"),
            {"selected": [bloque.pk, valide.pk], "bulk_statut": DossierCandidature.Statut.ACCEPTE},
        )

        bloque.refresh_from_db()
        valide.refresh_from_db()
        assert bloque.statut == DossierCandidature.Statut.SOUMIS
        assert bloque.utilisateur_cree is None
        assert valide.utilisateur_cree is not None

    def test_sans_promotion_active_le_dossier_reste_en_examen(self, client, secretaire, parcours, promotion):
        """Mieux vaut ne rien faire que verser un candidat dans une promotion close."""
        promotion.actif = False
        promotion.save(update_fields=["actif"])
        dossier = _dossier(parcours, "Sara", "Sanspromo")
        client.force_login(secretaire)

        client.post(
            reverse("administration:candidatures_bulk_status"),
            {"selected": [dossier.pk], "bulk_statut": DossierCandidature.Statut.ACCEPTE},
        )

        dossier.refresh_from_db()
        assert dossier.statut == DossierCandidature.Statut.EN_EXAMEN
        assert dossier.utilisateur_cree is None

    def test_les_autres_statuts_passent_toujours_par_la_machine_a_etats(self, client, secretaire, parcours):
        dossier = _dossier(parcours, "Luc", "Incomplet")
        client.force_login(secretaire)

        client.post(
            reverse("administration:candidatures_bulk_status"),
            {"selected": [dossier.pk], "bulk_statut": DossierCandidature.Statut.INCOMPLET},
        )

        dossier.refresh_from_db()
        assert dossier.statut == DossierCandidature.Statut.INCOMPLET
        assert dossier.utilisateur_cree is None

    def test_un_etudiant_ne_peut_pas_declencher_l_action(self, client, parcours, promotion, db):
        dossier = _dossier(parcours, "Zoé", "Intruse")
        intrus = User.objects.create_user(
            username="intrus-groupee",
            email="intrus-groupee@iteag.org",
            password="motdepasse-long-12",
            role=User.Role.ETUDIANT,
        )
        client.force_login(intrus)

        client.post(
            reverse("administration:candidatures_bulk_status"),
            {"selected": [dossier.pk], "bulk_statut": DossierCandidature.Statut.ACCEPTE},
        )

        dossier.refresh_from_db()
        assert dossier.statut == DossierCandidature.Statut.EN_EXAMEN


@pytest.mark.django_db
class TestRattrapageDesComptes:
    """La commande répare ce que l'action groupée fautive a laissé derrière elle."""

    def test_recree_le_compte_d_un_dossier_accepte_sans_utilisateur(self, parcours, promotion):
        dossier = _dossier(parcours, "Orpheline", "Candidature", statut=DossierCandidature.Statut.ACCEPTE)

        call_command("rattraper_comptes_acceptes", verbosity=0)

        dossier.refresh_from_db()
        assert dossier.utilisateur_cree is not None
        assert dossier.utilisateur_cree.profil_etudiant.promotion == promotion

    def test_est_idempotente(self, parcours, promotion):
        dossier = _dossier(parcours, "Deuxfois", "Candidature", statut=DossierCandidature.Statut.ACCEPTE)

        call_command("rattraper_comptes_acceptes", verbosity=0)
        dossier.refresh_from_db()
        compte = dossier.utilisateur_cree

        call_command("rattraper_comptes_acceptes", verbosity=0)
        dossier.refresh_from_db()
        assert dossier.utilisateur_cree == compte
        assert User.objects.filter(email=dossier.email).count() == 1

    def test_ne_touche_pas_aux_dossiers_deja_pourvus(self, parcours, promotion, dossier):
        profil = accepter_dossier(dossier, promotion=promotion)

        call_command("rattraper_comptes_acceptes", verbosity=0)

        dossier.refresh_from_db()
        assert dossier.utilisateur_cree == profil.utilisateur
        assert ProfilEtudiant.objects.count() == 1

    def test_la_simulation_ne_cree_rien(self, parcours, promotion):
        dossier = _dossier(parcours, "Simulee", "Candidature", statut=DossierCandidature.Statut.ACCEPTE)

        call_command("rattraper_comptes_acceptes", "--simuler", verbosity=0)

        dossier.refresh_from_db()
        assert dossier.utilisateur_cree is None
