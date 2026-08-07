from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.academics.models import (
    CoursDeSession,
    DemandeInscriptionCours,
    Paiement,
    SessionAcademique,
)
from apps.accounts.models import User
from apps.formations.models import Cours, Discipline
from apps.paiements.models import Reglement
from apps.paiements.models_inscriptions import ReglementInscription
from apps.paiements.services import attribution, reglements

pytestmark = pytest.mark.django_db


@pytest.fixture
def demande_inscription(etudiant, professeur):
    discipline = Discipline.objects.create(
        nom="Paiement des inscriptions",
        slug="paiement-inscriptions",
    )
    cours = Cours.objects.create(
        titre="Herméneutique appliquée",
        slug="hermeneutique-paiement",
        discipline=discipline,
    )
    cours.parcours.add(etudiant.parcours)
    debut = date.today() + timedelta(days=20)
    session = SessionAcademique.objects.create(
        nom="Session paiement",
        periode=SessionAcademique.Periode.CARNAVAL,
        annee_academique="2026-2027",
        date_debut=debut,
        date_fin=debut + timedelta(days=7),
    )
    offre = CoursDeSession.objects.create(
        session=session,
        cours=cours,
        enseignant=professeur,
        frais_inscription=Decimal("85.00"),
    )
    return DemandeInscriptionCours.objects.create(
        etudiant=etudiant,
        cours_session=offre,
        statut=DemandeInscriptionCours.Statut.PAIEMENT_ATTENTE,
        montant_du=Decimal("85.00"),
    )


def test_bouton_payer_ouvre_le_checkout_de_la_bonne_demande(client, demande_inscription):
    client.force_login(demande_inscription.etudiant.utilisateur)

    reponse = client.post(
        reverse(
            "paiements:payer_inscription",
            kwargs={"pk": demande_inscription.pk},
        )
    )

    association = ReglementInscription.objects.select_related("reglement").get(demande=demande_inscription)
    assert reponse.status_code == 302
    assert reponse.url == reverse(
        "paiements:checkout",
        kwargs={"pk": association.reglement.pk},
    )
    assert association.reglement.nature == Reglement.Nature.FRAIS_INSCRIPTION
    assert association.reglement.montant_ttc == Decimal("85.00")


def test_un_etudiant_ne_peut_pas_payer_la_demande_d_un_autre(client, demande_inscription):
    tiers = User.objects.create_user(
        username="tiers_paiement_inscription",
        email="tiers-paiement@iteag.org",
        password="motdepasse-long-12",
        role=User.Role.ETUDIANT,
    )
    client.force_login(tiers)

    reponse = client.post(
        reverse(
            "paiements:payer_inscription",
            kwargs={"pk": demande_inscription.pk},
        )
    )

    assert reponse.status_code == 404
    assert not ReglementInscription.objects.filter(demande=demande_inscription).exists()


def test_le_paiement_stripe_est_rattache_a_la_session_et_a_la_demande(demande_inscription):
    reglement = reglements.pour_demande_inscription(
        demande_inscription,
        utilisateur=demande_inscription.etudiant.utilisateur,
    )
    reglement.statut = Reglement.Statut.PAYE
    reglement.save(update_fields=["statut", "updated_at"])

    attribution.delivrer(reglement)

    paiement = Paiement.objects.get(reference=str(reglement.pk))
    demande_inscription.refresh_from_db()
    assert paiement.session == demande_inscription.cours_session.session
    assert paiement.statut == Paiement.StatutPaiement.CONFIRME
    assert demande_inscription.paiement == paiement
    assert demande_inscription.reference_paiement == str(reglement.pk)
    assert demande_inscription.statut == DemandeInscriptionCours.Statut.PAIEMENT_ATTENTE


def test_le_bouton_disparait_apres_confirmation_du_paiement(client, demande_inscription):
    client.force_login(demande_inscription.etudiant.utilisateur)

    demandes = client.get(reverse("etudiant:enrollment_requests"))
    paiements = client.get(reverse("etudiant:payments"))
    assert "Payer maintenant" in demandes.content.decode()
    assert "Payer maintenant" in paiements.content.decode()

    reglement = reglements.pour_demande_inscription(
        demande_inscription,
        utilisateur=demande_inscription.etudiant.utilisateur,
    )
    reglement.statut = Reglement.Statut.PAYE
    reglement.save(update_fields=["statut", "updated_at"])
    attribution.delivrer(reglement)

    demandes = client.get(reverse("etudiant:enrollment_requests"))
    paiements = client.get(reverse("etudiant:payments"))
    assert "Payer maintenant" not in demandes.content.decode()
    assert "Payer maintenant" not in paiements.content.decode()
    assert "Paiement reçu" in demandes.content.decode()
