"""
Les chiffres du tableau de bord doivent être vrais.

Un indicateur faux est pire qu'un indicateur absent : il oriente une décision.
Ces tests fixent donc, pour chaque montant, **ce qu'il compte et ce qu'il ne
compte pas** — c'est la définition de gestion qui est protégée ici, pas la
mécanique de la requête.

Le cas qui a motivé le découpage : « restant dû » ne doit pas inclure les
demandes confirmées. Une confirmation atteste que le règlement a été reçu ou
l'exonération accordée ; les compter encore doublerait la créance à l'écran.
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.academics.models import (
    CoursDeSession,
    DemandeInscriptionCours,
    InscriptionSession,
    Paiement,
    ProfilEtudiant,
    Promotion,
    SessionAcademique,
)
from apps.accounts.models import User
from apps.administration.services import pilotage
from apps.formations.models import Cours, Discipline, Parcours, Professeur
from apps.lms.models import Evaluation


@pytest.fixture
def univers(db):
    parcours = Parcours.objects.create(
        nom="Diplômant", slug="diplomant-pilotage", type_parcours=Parcours.TypeParcours.DIPLOMANT_ITEAG
    )
    promotion = Promotion.objects.create(nom="Promo pilotage", parcours=parcours, annee_debut=2027, annee_fin=2033)
    discipline = Discipline.objects.create(nom="Dogmatique", slug="dogmatique-pil")
    utilisateur_prof = User.objects.create_user(
        username="prof_pil", email="pp@iteag.org", password="motdepasse-long-12", role=User.Role.ENSEIGNANT
    )
    professeur = Professeur.objects.create(user=utilisateur_prof, nom="Léger", prenom="Paul", slug="paul-leger")
    cours = Cours.objects.create(titre="Le Credo", slug="le-credo", discipline=discipline)

    aujourd_hui = timezone.localdate()
    session = SessionAcademique.objects.create(
        nom="Session pilotage",
        periode=SessionAcademique.Periode.TOUSSAINT,
        annee_academique="2027-2028",
        date_debut=aujourd_hui - timedelta(days=2),
        date_fin=aujourd_hui + timedelta(days=20),
    )
    offre = CoursDeSession.objects.create(session=session, cours=cours, enseignant=professeur)

    utilisateur = User.objects.create_user(
        username="etu_pil",
        email="ep@iteag.org",
        password="motdepasse-long-12",
        first_name="Nadia",
        last_name="Roche",
        role=User.Role.ETUDIANT,
    )
    etudiant = ProfilEtudiant.objects.create(
        utilisateur=utilisateur,
        parcours=parcours,
        promotion=promotion,
        numero_etudiant="ETU-PIL-1",
        statut_inscription=ProfilEtudiant.StatutInscription.ACTIF,
    )
    return {
        "session": session,
        "offre": offre,
        "etudiant": etudiant,
        "parcours": parcours,
        "professeur": professeur,
    }


def paiement(etudiant, session, montant, statut):
    return Paiement.objects.create(
        etudiant=etudiant,
        session=session,
        montant=Decimal(montant),
        date_paiement=timezone.localdate(),
        mode=Paiement.ModePaiement.VIREMENT,
        statut=statut,
    )


# ══════════════════════════════════════════════
# Finances
# ══════════════════════════════════════════════


@pytest.mark.django_db
class TestFinances:
    def test_seuls_les_paiements_confirmes_sont_encaisses(self, univers):
        paiement(univers["etudiant"], univers["session"], "120.00", Paiement.StatutPaiement.CONFIRME)
        paiement(univers["etudiant"], univers["session"], "80.00", Paiement.StatutPaiement.EN_ATTENTE)
        chiffres = pilotage.finances()
        assert chiffres["encaisse_total"] == Decimal("120.00")
        assert chiffres["annonce_total"] == Decimal("80.00")

    def test_le_restant_du_agrege_les_demandes_non_soldees(self, univers):
        DemandeInscriptionCours.objects.create(
            etudiant=univers["etudiant"],
            cours_session=univers["offre"],
            montant_du=Decimal("250.00"),
            statut=DemandeInscriptionCours.Statut.PAIEMENT_ATTENTE,
        )
        chiffres = pilotage.finances()
        assert chiffres["restant_du_total"] == Decimal("250.00")
        assert chiffres["relance_total"] == Decimal("250.00")

    def test_une_demande_confirmee_ne_reste_pas_due(self, univers):
        """
        Le cas qui compte : une confirmation atteste du règlement ou de
        l'exonération. La compter encore doublerait la créance à l'écran.
        """
        DemandeInscriptionCours.objects.create(
            etudiant=univers["etudiant"],
            cours_session=univers["offre"],
            montant_du=Decimal("250.00"),
            statut=DemandeInscriptionCours.Statut.CONFIRMEE,
        )
        assert pilotage.finances()["restant_du_total"] == Decimal("0.00")

    def test_une_demande_soumise_est_due_mais_pas_encore_relancable(self, univers):
        DemandeInscriptionCours.objects.create(
            etudiant=univers["etudiant"],
            cours_session=univers["offre"],
            montant_du=Decimal("90.00"),
            statut=DemandeInscriptionCours.Statut.SOUMISE,
        )
        chiffres = pilotage.finances()
        assert chiffres["restant_du_total"] == Decimal("90.00")
        assert chiffres["relance_total"] == Decimal("0.00")

    def test_sans_donnee_les_montants_valent_zero(self, db):
        """Un tableau vide affiche zéro, pas « None » ni une case blanche."""
        chiffres = pilotage.finances()
        assert chiffres["encaisse_total"] == Decimal("0.00")
        assert chiffres["restant_du_total"] == Decimal("0.00")

    def test_l_encaisse_de_session_ne_retient_que_cette_session(self, univers):
        autre = SessionAcademique.objects.create(
            nom="Autre session",
            periode=SessionAcademique.Periode.PAQUES,
            annee_academique="2028-2029",
            date_debut=timezone.localdate() + timedelta(days=200),
            date_fin=timezone.localdate() + timedelta(days=210),
        )
        paiement(univers["etudiant"], univers["session"], "100.00", Paiement.StatutPaiement.CONFIRME)
        paiement(univers["etudiant"], autre, "500.00", Paiement.StatutPaiement.CONFIRME)
        chiffres = pilotage.finances(session_en_cours=univers["session"])
        assert chiffres["encaisse_session"] == Decimal("100.00")
        assert chiffres["encaisse_total"] == Decimal("600.00")


# ══════════════════════════════════════════════
# Résultats
# ══════════════════════════════════════════════


@pytest.mark.django_db
class TestResultats:
    def test_la_moyenne_ne_porte_que_sur_les_notes_publiees(self, univers):
        """
        Une note en correction n'est pas un résultat : la compter ferait bouger
        la moyenne sans qu'aucun étudiant n'ait rien passé.
        """
        Evaluation.objects.create(
            etudiant=univers["etudiant"],
            cours_session=univers["offre"],
            note=Decimal("16.00"),
            statut=Evaluation.StatutEvaluation.PUBLIE,
        )
        Evaluation.objects.create(
            etudiant=univers["etudiant"],
            cours_session=univers["offre"],
            note=Decimal("2.00"),
            statut=Evaluation.StatutEvaluation.EN_CORRECTION,
        )
        chiffres = pilotage.resultats()
        assert chiffres["note_moyenne"] == Decimal("16.00")
        assert chiffres["notes_publiees"] == 1

    def test_sans_note_publiee_aucune_moyenne_n_est_affichee(self, univers):
        """« 0/20 » se lirait comme un désastre là où il n'y a rien à montrer."""
        assert pilotage.resultats()["note_moyenne"] is None

    def test_les_copies_remises_sont_comptees(self, univers):
        Evaluation.objects.create(
            etudiant=univers["etudiant"],
            cours_session=univers["offre"],
            statut=Evaluation.StatutEvaluation.SOUMIS,
        )
        assert pilotage.resultats()["copies_a_corriger"] == 1


# ══════════════════════════════════════════════
# Activité et échéances
# ══════════════════════════════════════════════


@pytest.mark.django_db
class TestActivite:
    def test_les_cours_sont_repartis_selon_les_dates(self, univers):
        assert pilotage.formations()["cours_en_cours"] == 1
        assert pilotage.formations()["cours_a_venir"] == 0

    def test_un_etudiant_inscrit_est_compte_une_fois(self, univers):
        InscriptionSession.objects.create(etudiant=univers["etudiant"], cours_session=univers["offre"])
        assert pilotage.formations()["inscriptions_actives"] == 1


@pytest.mark.django_db
class TestEcheances:
    def test_une_cloture_proche_remonte(self, univers):
        univers["offre"].date_limite_inscription = timezone.localdate() + timedelta(days=5)
        univers["offre"].save(update_fields=["date_limite_inscription"])
        trouvees = pilotage.echeances()
        assert any("Clôture" in echeance.libelle for echeance in trouvees)
        assert trouvees[0].jours_restants == 5

    def test_une_cloture_lointaine_ne_remonte_pas(self, univers):
        """L'horizon existe pour que la liste reste lisible."""
        univers["offre"].date_limite_inscription = timezone.localdate() + timedelta(days=400)
        univers["offre"].save(update_fields=["date_limite_inscription"])
        assert pilotage.echeances() == []

    def test_une_date_passee_ne_remonte_pas(self, univers):
        univers["offre"].date_limite_inscription = timezone.localdate() - timedelta(days=1)
        univers["offre"].save(update_fields=["date_limite_inscription"])
        assert pilotage.echeances() == []


# ══════════════════════════════════════════════
# Alertes
# ══════════════════════════════════════════════


@pytest.mark.django_db
class TestAlertes:
    def test_sans_rien_a_faire_aucune_alerte(self, db):
        """Un tableau constellé de compteurs à zéro cesse d'être lu."""
        assert pilotage.alertes() == []

    def test_une_demande_d_inscription_declenche_une_alerte(self, univers):
        DemandeInscriptionCours.objects.create(
            etudiant=univers["etudiant"],
            cours_session=univers["offre"],
            montant_du=Decimal("0.00"),
            statut=DemandeInscriptionCours.Statut.SOUMISE,
        )
        alertes = pilotage.alertes()
        assert len(alertes) == 1
        assert alertes[0].nombre == 1
        assert alertes[0].urgent is True

    def test_un_cours_complet_encore_ouvert_est_signale(self, univers):
        """Il renvoie l'étudiant sur un refus : quelqu'un doit trancher."""
        univers["offre"].capacite = 1
        univers["offre"].save(update_fields=["capacite"])
        InscriptionSession.objects.create(etudiant=univers["etudiant"], cours_session=univers["offre"])
        assert any("complet" in alerte.libelle for alerte in pilotage.alertes())


# ══════════════════════════════════════════════
# Rendu
# ══════════════════════════════════════════════


@pytest.mark.django_db
class TestRenduDuTableauDeBord:
    @pytest.fixture
    def administrateur(self, db):
        return User.objects.create_user(
            username="admin_pil", email="ap@iteag.org", password="motdepasse-long-12", role=User.Role.ADMIN
        )

    def test_les_montants_reels_apparaissent(self, client, administrateur, univers):
        paiement(univers["etudiant"], univers["session"], "340.00", Paiement.StatutPaiement.CONFIRME)
        client.force_login(administrateur)
        contenu = client.get(reverse("administration:dashboard")).content.decode()
        assert "340,00 €" in contenu

    def test_le_cout_ne_croit_pas_avec_le_volume(self, client, administrateur, univers):
        """Ajouter des indicateurs ne doit pas rendre l'écran coûteux."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        client.force_login(administrateur)
        paiement(univers["etudiant"], univers["session"], "10.00", Paiement.StatutPaiement.CONFIRME)
        with CaptureQueriesContext(connection) as capture:
            client.get(reverse("administration:dashboard"))
        petit = len(capture)

        for _ in range(30):
            paiement(univers["etudiant"], univers["session"], "10.00", Paiement.StatutPaiement.CONFIRME)
        with CaptureQueriesContext(connection) as capture:
            client.get(reverse("administration:dashboard"))
        grand = len(capture)

        assert grand - petit <= 2, f"{petit} requêtes pour 1 paiement, {grand} pour 31"
