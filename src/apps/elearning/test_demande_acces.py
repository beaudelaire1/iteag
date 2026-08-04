"""
Demande d'accès à un module par un étudiant déjà inscrit à l'institut.

Le défaut corrigé ici : le seul appel à l'action offert à un étudiant devant un
module fermé était « Déposer une candidature » — le formulaire public
d'admission, qui redemande nom, prénom, date de naissance, pièce d'identité et
diplômes. À quelqu'un dont l'ITEAG détient déjà le dossier.

Ce que ces tests protègent :

1. l'étudiant connu demande en **un clic**, sans ressaisir aucune coordonnée ;
2. la demande **n'ouvre rien** tant que le secrétariat n'a pas tranché — c'est
   le point où un raccourci créerait une fuite d'accès ;
3. le secrétariat peut accorder ou refuser, et l'étudiant en est averti.
"""

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse

from apps.academics.models import ProfilEtudiant, Promotion
from apps.accounts.models import User
from apps.core.models import Notification
from apps.elearning.models import InscriptionModule, ModuleFormation
from apps.elearning.services import octroi
from apps.elearning.services.acces import verifier_acces
from apps.formations.models import Discipline, Parcours, Professeur


@pytest.fixture
def parcours(db):
    return Parcours.objects.create(
        nom="Diplômant", slug="diplomant-demande", type_parcours=Parcours.TypeParcours.DIPLOMANT_ITEAG
    )


@pytest.fixture
def etudiant(db, parcours):
    promotion = Promotion.objects.create(nom="Promo demande", parcours=parcours, annee_debut=2027, annee_fin=2033)
    utilisateur = User.objects.create_user(
        username="etu_demande",
        email="etu_demande@iteag.org",
        password="motdepasse-long-12",
        first_name="Rose",
        last_name="Delmas",
        role=User.Role.ETUDIANT,
    )
    return ProfilEtudiant.objects.create(
        utilisateur=utilisateur,
        parcours=parcours,
        promotion=promotion,
        numero_etudiant="ETU-DEM-001",
        statut_inscription=ProfilEtudiant.StatutInscription.ACTIF,
    )


@pytest.fixture
def module(db):
    discipline = Discipline.objects.create(nom="Patristique", slug="patristique-dem")
    utilisateur = User.objects.create_user(
        username="prof_dem", email="prof_dem@iteag.org", password="motdepasse-long-12", role=User.Role.ENSEIGNANT
    )
    professeur = Professeur.objects.create(user=utilisateur, nom="Sylvain", prenom="Marc", slug="marc-sylvain")
    return ModuleFormation.objects.create(
        titre="Les Pères de l'Église",
        slug="peres-de-l-eglise",
        discipline=discipline,
        responsable=professeur,
        statut=ModuleFormation.StatutPublication.PUBLIE,
        politique_acces=ModuleFormation.PolitiqueAcces.SUR_OCTROI,
    )


@pytest.fixture
def lecon(db, module):
    from apps.elearning.models import Chapitre, Lecon

    chapitre = Chapitre.objects.create(module=module, titre="Introduction", ordre=1)
    return Lecon.objects.create(chapitre=chapitre, titre="Ignace d'Antioche", slug="ignace-antioche", ordre=1)


@pytest.fixture
def secretaire(db):
    return User.objects.create_user(
        username="secretaire_dem",
        email="sec_dem@iteag.org",
        password="motdepasse-long-12",
        role=User.Role.SECRETARIAT,
    )


# ══════════════════════════════════════════════
# Le geste de l'étudiant
# ══════════════════════════════════════════════


@pytest.mark.django_db
class TestDemandeEnUnClic:
    def test_la_fiche_module_propose_de_demander_l_acces(self, client, etudiant, module):
        """Le défaut d'origine : cette page renvoyait vers le dossier d'admission."""
        client.force_login(etudiant.utilisateur)
        contenu = client.get(module.get_absolute_url()).content.decode()
        assert "Demander l'accès" in contenu
        assert reverse("elearning:module_demander_acces", args=[module.slug]) in contenu

    def test_le_dossier_d_admission_n_est_plus_propose_a_un_inscrit(self, client, etudiant, module):
        """
        Le cœur de la correction : on ne redemande pas une candidature à
        quelqu'un dont on détient déjà le dossier.
        """
        client.force_login(etudiant.utilisateur)
        contenu = client.get(module.get_absolute_url()).content.decode()
        assert "Déposer une candidature" not in contenu

    def test_un_visiteur_sans_compte_reste_invite_a_candidater(self, client, module):
        """La voie d'admission demeure — pour ceux qui ne sont pas encore inscrits."""
        contenu = client.get(module.get_absolute_url()).content.decode()
        assert "Déposer une candidature" in contenu

    def test_la_demande_ne_reclame_aucune_donnee(self, client, etudiant, module):
        """Un POST vide suffit : c'est la définition du « un clic »."""
        client.force_login(etudiant.utilisateur)
        reponse = client.post(reverse("elearning:module_demander_acces", args=[module.slug]))
        assert reponse.status_code == 302
        assert InscriptionModule.objects.filter(etudiant=etudiant, module=module).exists()

    def test_la_demande_est_visible_dans_mes_formations(self, client, etudiant, module):
        octroi.demander(etudiant, module)
        client.force_login(etudiant.utilisateur)
        contexte = client.get(reverse("elearning:mes_formations")).context
        assert [i.module for i in contexte["demandes"]] == [module]

    def test_le_refus_de_lecture_propose_la_demande(self, client, etudiant, module, lecon):
        """
        Un refus doit offrir la voie de sortie la plus courte. Elle pointait
        elle aussi vers le dossier d'admission.
        """
        client.force_login(etudiant.utilisateur)
        reponse = client.get(reverse("elearning:lecon_detail", args=[module.slug, lecon.slug]))
        assert reponse.status_code == 403
        assert "Demander l'accès à ce module" in reponse.content.decode()


# ══════════════════════════════════════════════
# Ce qu'une demande n'ouvre pas
# ══════════════════════════════════════════════


@pytest.mark.django_db
class TestUneDemandeNOuvreRien:
    def test_le_droit_existe_sans_etre_exercable(self, etudiant, module):
        inscription = octroi.demander(etudiant, module)
        assert inscription.statut == InscriptionModule.StatutAcces.DEMANDE
        assert inscription.est_active() is False

    def test_la_lecture_reste_refusee(self, etudiant, module, lecon):
        """Le point exact où un raccourci créerait une fuite d'accès."""
        octroi.demander(etudiant, module)
        assert verifier_acces(etudiant.utilisateur, lecon).autorise is False

    def test_le_tableau_de_bord_ne_la_compte_pas_comme_en_cours(self, client, etudiant, module):
        octroi.demander(etudiant, module)
        client.force_login(etudiant.utilisateur)
        contexte = client.get(reverse("etudiant:dashboard")).context
        assert list(contexte["modules_en_cours"]) == []


# ══════════════════════════════════════════════
# Recevabilité
# ══════════════════════════════════════════════


@pytest.mark.django_db
class TestRecevabilite:
    def test_un_module_non_publie_ne_se_demande_pas(self, etudiant, module):
        module.statut = ModuleFormation.StatutPublication.BROUILLON
        module.save(update_fields=["statut"])
        with pytest.raises(ValidationError):
            octroi.demander(etudiant, module)

    def test_un_etudiant_suspendu_ne_demande_pas(self, etudiant, module):
        etudiant.statut_inscription = ProfilEtudiant.StatutInscription.SUSPENDU
        etudiant.save(update_fields=["statut_inscription"])
        with pytest.raises(ValidationError):
            octroi.demander(etudiant, module)

    def test_une_seconde_demande_est_refusee(self, etudiant, module):
        octroi.demander(etudiant, module)
        with pytest.raises(ValidationError):
            octroi.demander(etudiant, module)

    def test_un_module_deja_ouvert_ne_se_demande_pas(self, etudiant, module):
        octroi.octroyer(etudiant, module)
        with pytest.raises(ValidationError):
            octroi.demander(etudiant, module)

    def test_un_module_public_ne_se_demande_pas(self, etudiant, module):
        module.politique_acces = ModuleFormation.PolitiqueAcces.PUBLIC
        module.save(update_fields=["politique_acces"])
        with pytest.raises(ValidationError):
            octroi.demander(etudiant, module)

    def test_une_demande_peut_etre_renouvelee_apres_un_refus(self, etudiant, module, secretaire):
        """Un refus n'est pas définitif : la situation de l'étudiant peut changer."""
        inscription = octroi.demander(etudiant, module)
        octroi.refuser_demande(inscription, motif="Prérequis manquant", par=secretaire)
        renouvelee = octroi.demander(etudiant, module)
        assert renouvelee.statut == InscriptionModule.StatutAcces.DEMANDE
        assert renouvelee.motif_revocation == ""
        assert InscriptionModule.objects.filter(etudiant=etudiant, module=module).count() == 1


# ══════════════════════════════════════════════
# La décision du secrétariat
# ══════════════════════════════════════════════


@pytest.mark.django_db
class TestDecisionDuSecretariat:
    def test_le_secretariat_est_prevenu(self, etudiant, module, secretaire):
        """Une demande sans destinataire resterait sans réponse."""
        octroi.demander(etudiant, module)
        assert Notification.objects.filter(destinataire=secretaire).exists()

    def test_accorder_ouvre_reellement_l_acces(self, client, etudiant, module, secretaire, lecon):
        inscription = octroi.demander(etudiant, module)
        client.force_login(secretaire)
        client.post(
            reverse("administration:acces_action"),
            {"acces": [str(inscription.pk)], "action": "accorder"},
        )
        inscription.refresh_from_db()
        assert inscription.statut == InscriptionModule.StatutAcces.ACTIF
        assert verifier_acces(etudiant.utilisateur, lecon).autorise is True

    def test_refuser_ferme_et_explique(self, client, etudiant, module, secretaire):
        inscription = octroi.demander(etudiant, module)
        client.force_login(secretaire)
        client.post(
            reverse("administration:acces_action"),
            {"acces": [str(inscription.pk)], "action": "refuser", "motif": "Cursus incompatible"},
        )
        inscription.refresh_from_db()
        assert inscription.statut == InscriptionModule.StatutAcces.REVOQUE
        assert inscription.motif_revocation == "Cursus incompatible"
        # Le motif doit figurer dans le message, sans que sa formulation exacte
        # soit figée : ce qui compte est que le refus s'explique de lui-même.
        assert Notification.objects.filter(
            destinataire=etudiant.utilisateur, message__contains="Cursus incompatible"
        ).exists()

    def test_un_refus_sans_motif_ne_passe_pas(self, client, etudiant, module, secretaire):
        """Un refus muet est inexploitable — pour l'étudiant comme pour l'audit."""
        inscription = octroi.demander(etudiant, module)
        client.force_login(secretaire)
        client.post(
            reverse("administration:acces_action"),
            {"acces": [str(inscription.pk)], "action": "refuser", "motif": "   "},
        )
        inscription.refresh_from_db()
        assert inscription.statut == InscriptionModule.StatutAcces.DEMANDE

    def test_les_demandes_remontent_au_tableau_de_bord(self, client, etudiant, module, db):
        octroi.demander(etudiant, module)
        administrateur = User.objects.create_user(
            username="admin_dem", email="ad@iteag.org", password="motdepasse-long-12", role=User.Role.ADMIN
        )
        client.force_login(administrateur)
        assert client.get(reverse("administration:dashboard")).context["demandes_acces_video"] == 1

    def test_l_etudiant_ne_peut_pas_s_accorder_l_acces(self, client, etudiant, module):
        """Le cloisonnement vaut aussi pour cette action-ci."""
        inscription = octroi.demander(etudiant, module)
        client.force_login(etudiant.utilisateur)
        client.post(
            reverse("administration:acces_action"),
            {"acces": [str(inscription.pk)], "action": "accorder"},
        )
        inscription.refresh_from_db()
        assert inscription.statut == InscriptionModule.StatutAcces.DEMANDE


# ══════════════════════════════════════════════
# Le formulaire d'inscription au présentiel
# ══════════════════════════════════════════════


@pytest.mark.django_db
class TestInscriptionAuPresentielSansRessaisie:
    """Même principe pour les cours en session : rien de ce qui est au dossier n'est redemandé."""

    @pytest.fixture
    def offre(self, db, parcours, module):
        from apps.academics.models import CoursDeSession, SessionAcademique
        from apps.formations.models import Cours, Discipline

        discipline = Discipline.objects.create(nom="Exégèse", slug="exegese-dem")
        cours = Cours.objects.create(titre="Lecture de Marc", slug="lecture-marc", discipline=discipline)
        session = SessionAcademique.objects.create(
            nom="Session de Pâques",
            periode=SessionAcademique.Periode.PAQUES,
            annee_academique="2027-2028",
            date_debut="2028-04-03",
            date_fin="2028-04-08",
        )
        return CoursDeSession.objects.create(session=session, cours=cours, enseignant=module.responsable)

    def _fiche(self, client, etudiant, offre) -> str:
        client.force_login(etudiant.utilisateur)
        reponse = client.get(reverse("etudiant:course_offering_detail", args=[offre.pk]))
        assert reponse.status_code == 200
        return reponse.content.decode()

    def _formulaire(self, client, etudiant, offre) -> str:
        """Le seul formulaire de demande — pas l'infolettre du pied de page."""
        action = reverse("etudiant:enrollment_request_create", args=[offre.pk])
        contenu = self._fiche(client, etudiant, offre)
        assert action in contenu
        return contenu.split(action, 1)[1].split("</form>", 1)[0]

    def test_aucun_champ_d_identite_n_est_demande(self, client, etudiant, offre):
        formulaire = self._formulaire(client, etudiant, offre)
        for champ in ('name="nom"', 'name="prenom"', 'name="email"', 'name="date_naissance"'):
            assert champ not in formulaire, champ

    def test_le_dossier_connu_est_rappele(self, client, etudiant, offre):
        """L'étudiant doit voir que l'institut le connaît, pas seulement le supposer."""
        contenu = self._fiche(client, etudiant, offre)
        assert etudiant.numero_etudiant in contenu
        assert "Rose Delmas" in contenu

    def test_sans_frais_le_reglement_n_est_pas_demande(self, client, etudiant, offre):
        formulaire = self._formulaire(client, etudiant, offre)
        assert "justificatif_paiement" not in formulaire
        assert "Confirmer ma demande" in formulaire

    def test_la_demande_aboutit_sans_aucun_champ_rempli(self, client, etudiant, offre):
        from apps.academics.models import DemandeInscriptionCours

        client.force_login(etudiant.utilisateur)
        client.post(reverse("etudiant:enrollment_request_create", args=[offre.pk]))
        assert DemandeInscriptionCours.objects.filter(etudiant=etudiant, cours_session=offre).exists()
