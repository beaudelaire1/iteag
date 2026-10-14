"""Tests des paiements affectés aux cours et aux ateliers."""
from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.accounts.models import User
from apps.academics.models import CoursDeSession, DemandeInscriptionCours, Paiement, ProfilEtudiant, SessionAcademique
from apps.academics.services.inscriptions import _paiement_confirme_compatible
from apps.administration.forms import EnrollmentDecisionForm, PaiementForm
from apps.formations.models import Cours, Discipline, Professeur


@pytest.fixture
def exemple(db):
    agent = User.objects.create_user(username="agent_ateliers", role=User.Role.SECRETARIAT)
    user = User.objects.create_user(username="eleve_ateliers", role=User.Role.ETUDIANT)
    profil = ProfilEtudiant.objects.create(utilisateur=user, numero_etudiant="AT-123")
    discipline = Discipline.objects.create(nom="Théologie des ateliers", slug="test-theologie-ateliers")
    enseignant = Professeur.objects.create(nom="Enseignant", prenom="Test", slug="test-enseignant-ateliers")
    session = SessionAcademique.objects.create(
        nom="Ateliers 2026-2027", periode="ateliers", annee_academique="2026-2027",
        date_debut=date(2026, 9, 26), date_fin=date(2027, 6, 19),
    )
    cours = [
        Cours.objects.create(titre=t, slug=f"test-atelier-{i}", discipline=discipline)
        for i, t in enumerate(("Atelier de théologie", "Un autre atelier", "Cours annoncé"))
    ]
    offres = [CoursDeSession.objects.create(session=session, cours=c, enseignant=enseignant) for c in cours[:2]]
    return agent, profil, session, offres, cours[2]


@pytest.mark.django_db
def test_paiement_affecte_et_activite_non_programmee(exemple):
    agent, profil, session, offres, annonce = exemple
    form = PaiementForm(data={
        "etudiant": profil.pk, "montant": "200", "date_paiement": "2026-10-14",
        "mode": "virement", "statut": "confirme", "cours_session": offres[0].pk,
    })
    assert form.is_valid(), form.errors
    paiement = form.save()
    assert paiement.session == session
    assert paiement.cours_session == offres[0]
    assert all(x.cours_id != annonce.pk for x in form.fields["cours_session"].queryset)


@pytest.mark.django_db
def test_paiement_atelier_non_reutilisable_pour_un_autre(exemple):
    agent, profil, session, offres, annonce = exemple
    paiement = Paiement.objects.create(
        etudiant=profil, session=session, cours_session=offres[0],
        date_paiement=date(2026, 10, 14), montant=Decimal("200"),
        mode="virement", statut="confirme",
    )
    demande = DemandeInscriptionCours.objects.create(
        etudiant=profil, cours_session=offres[1], montant_du=Decimal("100"),
    )
    assert _paiement_confirme_compatible(demande) is None
    assert paiement not in EnrollmentDecisionForm(demande=demande).fields["paiement"].queryset


@pytest.mark.django_db
def test_liste_et_fiche_montrent_l_atelier(client, exemple):
    agent, profil, session, offres, annonce = exemple
    paiement = Paiement.objects.create(
        etudiant=profil, session=session, cours_session=offres[0],
        date_paiement=date(2026, 10, 14), montant=Decimal("200"),
        mode="virement", statut="confirme",
    )
    client.force_login(agent)
    liste = client.get(reverse("administration:payments"), {"q": "théologie"})
    assert liste.status_code == 200
    assert paiement in liste.context["paiements"]
    fiche = client.get(reverse("administration:etudiant_detail", args=[profil.pk]))
    assert offres[0].cours.titre in fiche.content.decode()
