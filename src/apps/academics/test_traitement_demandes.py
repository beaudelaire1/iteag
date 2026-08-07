from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.academics.models import CoursDeSession, DemandeInscriptionCours, ProfilEtudiant, Promotion, SessionAcademique
from apps.academics.services.inscriptions import traiter_demande
from apps.accounts.models import User
from apps.administration.forms import EnrollmentDecisionForm
from apps.formations.models import Cours, Discipline, Parcours, Professeur

pytestmark = pytest.mark.django_db


@pytest.fixture
def demande_a_traiter():
    parcours = Parcours.objects.create(
        nom="Parcours traitement",
        slug="parcours-traitement-demandes",
        type_parcours=Parcours.TypeParcours.LIBRE,
    )
    promotion = Promotion.objects.create(
        nom="Promotion traitement", parcours=parcours, annee_debut=2026, annee_fin=2028
    )
    compte = User.objects.create_user(username="etudiant-traitement", role=User.Role.ETUDIANT)
    etudiant = ProfilEtudiant.objects.create(
        utilisateur=compte,
        parcours=parcours,
        promotion=promotion,
        numero_etudiant="TRT-001",
        statut_inscription=ProfilEtudiant.StatutInscription.ACTIF,
    )
    discipline = Discipline.objects.create(nom="Traitement", slug="traitement-demandes")
    cours = Cours.objects.create(titre="Cours à traiter", slug="cours-a-traiter", discipline=discipline)
    cours.parcours.add(parcours)
    professeur = Professeur.objects.create(nom="Durand", prenom="Jeanne", slug="jeanne-durand-traitement")
    session = SessionAcademique.objects.create(
        nom="Session future",
        periode=SessionAcademique.Periode.TOUSSAINT,
        annee_academique="2026-2027",
        date_debut=timezone.localdate() + timedelta(days=30),
        date_fin=timezone.localdate() + timedelta(days=37),
    )
    offre = CoursDeSession.objects.create(
        session=session,
        cours=cours,
        enseignant=professeur,
        statut=CoursDeSession.StatutCours.EN_COURS,
        inscriptions_ouvertes=False,
        date_limite_inscription=timezone.localdate() - timedelta(days=1),
        frais_inscription=Decimal("0.00"),
    )
    demande = DemandeInscriptionCours.objects.create(etudiant=etudiant, cours_session=offre, montant_du=Decimal("0.00"))
    secretaire = User.objects.create_user(username="secretariat-traitement", role=User.Role.SECRETARIAT)
    return demande, secretaire


def test_confirmation_staff_ne_rejoue_pas_la_fenetre_publique(demande_a_traiter):
    demande, secretaire = demande_a_traiter
    traiter_demande(demande=demande, action="confirmer", par=secretaire)
    demande.refresh_from_db()
    assert demande.statut == DemandeInscriptionCours.Statut.CONFIRMEE
    assert demande.inscription.cours_session.session.date_fin > timezone.localdate()


def test_double_confirmation_idempotente(demande_a_traiter):
    demande, secretaire = demande_a_traiter
    traiter_demande(demande=demande, action="confirmer", par=secretaire)
    nombre_historique = demande.historique.count()
    traiter_demande(demande=demande, action="confirmer", par=secretaire)
    assert demande.historique.count() == nombre_historique


@pytest.mark.parametrize(
    ("statut", "actions"),
    [
        (DemandeInscriptionCours.Statut.SOUMISE, {"demander_paiement", "confirmer", "refuser"}),
        (DemandeInscriptionCours.Statut.PAIEMENT_ATTENTE, {"confirmer", "refuser"}),
        (DemandeInscriptionCours.Statut.CONFIRMEE, set()),
        (DemandeInscriptionCours.Statut.REFUSEE, {"reouvrir"}),
        (DemandeInscriptionCours.Statut.ANNULEE, {"reouvrir"}),
    ],
)
def test_formulaire_limite_les_transitions(demande_a_traiter, statut, actions):
    demande, _ = demande_a_traiter
    demande.statut = statut
    demande.save(update_fields=["statut", "updated_at"])
    formulaire = EnrollmentDecisionForm(demande=demande)
    assert {valeur for valeur, _ in formulaire.fields["action"].choices} == actions
