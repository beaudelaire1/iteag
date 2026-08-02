"""Proposer un cours plutôt que l'affecter d'autorité.

L'administration désignait l'enseignant d'un cours sans le lui demander : il le
découvrait sur son tableau de bord, et un refus se réglait par téléphone, sans
trace. Le cours ne change de main qu'à l'acceptation.
"""

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.academics.models import CoursDeSession, PropositionEnseignement, SessionAcademique
from apps.accounts.models import User
from apps.core.models import Notification
from apps.elearning.models import ModuleFormation
from apps.formations.models import Cours, Discipline, Professeur

pytestmark = pytest.mark.django_db

MOT_DE_PASSE = "motdepasse-long-12"


@pytest.fixture
def secretaire(db):
    return User.objects.create_user(
        username="sec", email="sec@iteag.org", password=MOT_DE_PASSE, role=User.Role.SECRETARIAT
    )


@pytest.fixture
def compte_enseignant(db):
    return User.objects.create_user(
        username="prof", email="prof@iteag.org", password=MOT_DE_PASSE, role=User.Role.ENSEIGNANT
    )


@pytest.fixture
def professeur(db, compte_enseignant):
    return Professeur.objects.create(nom="Nisus", prenom="Alain", slug="alain-nisus", user=compte_enseignant)


@pytest.fixture
def titulaire(db):
    return Professeur.objects.create(nom="Toussaint", prenom="Gérard", slug="gerard-toussaint")


@pytest.fixture
def offre(db, titulaire):
    discipline = Discipline.objects.create(nom="Théologie", slug="theologie")
    cours = Cours.objects.create(titre="Herméneutique", slug="hermeneutique", discipline=discipline)
    aujourd_hui = timezone.localdate()
    session = SessionAcademique.objects.create(
        nom="Session en cours",
        date_debut=aujourd_hui - timedelta(days=3),
        date_fin=aujourd_hui + timedelta(days=27),
    )
    return CoursDeSession.objects.create(session=session, cours=cours, enseignant=titulaire)


# ══════════════════════════════════════════════
# L'administration propose
# ══════════════════════════════════════════════


class TestProposition:
    def test_la_fiche_de_l_enseignant_s_ouvre_sans_formulaire_de_modification(self, client, secretaire, professeur):
        client.force_login(secretaire)
        reponse = client.get(reverse("administration:professeur_detail", args=[professeur.pk]))
        assert reponse.status_code == 200
        contenu = reponse.content.decode()
        assert "Alain Nisus" in contenu
        assert "prof@iteag.org" in contenu

    def test_proposer_n_affecte_pas_encore_le_cours(self, client, secretaire, professeur, offre, titulaire):
        client.force_login(secretaire)
        client.post(
            reverse("administration:professeur_proposer_cours", args=[professeur.pk]),
            {"cours_session": offre.pk, "message": "Votre spécialité."},
        )

        proposition = PropositionEnseignement.objects.get()
        assert proposition.statut == PropositionEnseignement.Statut.PROPOSEE
        offre.refresh_from_db()
        assert offre.enseignant == titulaire, "Le cours ne change de main qu'à l'acceptation"

    def test_l_enseignant_est_averti(self, client, secretaire, professeur, offre, compte_enseignant):
        client.force_login(secretaire)
        client.post(
            reverse("administration:professeur_proposer_cours", args=[professeur.pk]),
            {"cours_session": offre.pk},
        )
        avis = Notification.objects.filter(destinataire=compte_enseignant)
        assert avis.count() == 1
        assert "Herméneutique" in avis.get().titre

    def test_une_seconde_proposition_identique_est_refusee(self, client, secretaire, professeur, offre):
        client.force_login(secretaire)
        for _ in range(2):
            client.post(
                reverse("administration:professeur_proposer_cours", args=[professeur.pk]),
                {"cours_session": offre.pk},
            )
        assert PropositionEnseignement.objects.count() == 1

    def test_un_etudiant_ne_propose_rien(self, client, db, professeur, offre):
        intrus = User.objects.create_user(
            username="intrus", email="i@x.org", password=MOT_DE_PASSE, role=User.Role.ETUDIANT
        )
        client.force_login(intrus)
        reponse = client.post(
            reverse("administration:professeur_proposer_cours", args=[professeur.pk]),
            {"cours_session": offre.pk},
        )
        assert reponse.status_code in (302, 403)
        assert PropositionEnseignement.objects.count() == 0


# ══════════════════════════════════════════════
# L'enseignant répond
# ══════════════════════════════════════════════


class TestReponse:
    @pytest.fixture
    def proposition(self, professeur, offre, secretaire):
        return PropositionEnseignement.objects.create(
            cours_session=offre, professeur=professeur, proposee_par=secretaire
        )

    def test_accepter_affecte_le_cours(self, client, compte_enseignant, professeur, proposition, offre):
        client.force_login(compte_enseignant)
        client.post(
            reverse("enseignant:proposition_reponse", args=[proposition.pk]),
            {"action": "accepter"},
        )
        proposition.refresh_from_db()
        offre.refresh_from_db()
        assert proposition.statut == PropositionEnseignement.Statut.ACCEPTEE
        assert offre.enseignant == professeur

    def test_decliner_sans_motif_est_impossible(self, client, compte_enseignant, proposition, offre, titulaire):
        client.force_login(compte_enseignant)
        client.post(
            reverse("enseignant:proposition_reponse", args=[proposition.pk]),
            {"action": "decliner", "motif": "   "},
        )
        proposition.refresh_from_db()
        offre.refresh_from_db()
        assert proposition.statut == PropositionEnseignement.Statut.PROPOSEE
        assert offre.enseignant == titulaire

    def test_decliner_avec_motif_laisse_le_cours_en_place(
        self, client, compte_enseignant, proposition, offre, titulaire
    ):
        client.force_login(compte_enseignant)
        client.post(
            reverse("enseignant:proposition_reponse", args=[proposition.pk]),
            {"action": "decliner", "motif": "Je suis déjà sur deux sessions."},
        )
        proposition.refresh_from_db()
        offre.refresh_from_db()
        assert proposition.statut == PropositionEnseignement.Statut.DECLINEE
        assert proposition.motif_refus == "Je suis déjà sur deux sessions."
        assert offre.enseignant == titulaire

    def test_l_administration_est_avertie_de_la_reponse(self, client, compte_enseignant, proposition, secretaire):
        client.force_login(compte_enseignant)
        client.post(reverse("enseignant:proposition_reponse", args=[proposition.pk]), {"action": "accepter"})
        assert Notification.objects.filter(destinataire=secretaire).exists()

    def test_on_ne_repond_pas_a_la_place_d_un_collegue(self, client, db, proposition, offre, titulaire):
        """L'identifiant est devinable : seule la fiche rattachée au compte fait autorité."""
        autre_compte = User.objects.create_user(
            username="autre", email="a@x.org", password=MOT_DE_PASSE, role=User.Role.ENSEIGNANT
        )
        Professeur.objects.create(nom="Autre", prenom="Prof", slug="autre-prof", user=autre_compte)

        client.force_login(autre_compte)
        reponse = client.post(
            reverse("enseignant:proposition_reponse", args=[proposition.pk]),
            {"action": "accepter"},
        )
        assert reponse.status_code == 404
        offre.refresh_from_db()
        assert offre.enseignant == titulaire

    def test_repondre_deux_fois_ne_change_rien(self, client, compte_enseignant, proposition):
        client.force_login(compte_enseignant)
        url = reverse("enseignant:proposition_reponse", args=[proposition.pk])
        client.post(url, {"action": "accepter"})
        client.post(url, {"action": "decliner", "motif": "Finalement non"})
        proposition.refresh_from_db()
        assert proposition.statut == PropositionEnseignement.Statut.ACCEPTEE

    def test_la_file_montre_ce_qui_attend_une_decision(self, client, compte_enseignant, proposition):
        client.force_login(compte_enseignant)
        contenu = client.get(reverse("enseignant:propositions")).content.decode()
        assert "Herméneutique" in contenu
        assert "Accepter ce cours" in contenu


# ══════════════════════════════════════════════
# Modules e-learning
# ══════════════════════════════════════════════


class TestAssociationModule:
    @pytest.fixture
    def module(self, db):
        discipline = Discipline.objects.create(nom="Exégèse", slug="exegese")
        return ModuleFormation.objects.create(titre="Exégèse du NT", slug="exegese-nt", discipline=discipline)

    def test_l_administration_confie_un_module(self, client, secretaire, professeur, module, compte_enseignant):
        client.force_login(secretaire)
        client.post(
            reverse("administration:professeur_associer_module", args=[professeur.pk]),
            {"module": module.pk},
        )
        module.refresh_from_db()
        assert module.responsable == professeur
        assert Notification.objects.filter(destinataire=compte_enseignant).exists()

    def test_l_administration_retire_un_module(self, client, secretaire, professeur, module):
        module.responsable = professeur
        module.save(update_fields=["responsable"])

        client.force_login(secretaire)
        client.post(
            reverse("administration:professeur_associer_module", args=[professeur.pk]),
            {"module": module.pk, "action": "retirer"},
        )
        module.refresh_from_db()
        assert module.responsable is None
