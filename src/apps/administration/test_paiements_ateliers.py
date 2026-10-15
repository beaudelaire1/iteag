"""Tests des paiements affectés aux cours et aux ateliers."""
from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.academics.models import (
    CoursDeSession,
    DemandeInscriptionCours,
    Paiement,
    ProfilEtudiant,
    SessionAcademique,
)
from apps.academics.services.inscriptions import _paiement_confirme_compatible
from apps.accounts.models import User
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
        nom="Ateliers 2032-2033",
        periode="ateliers",
        annee_academique="2032-2033",
        date_debut=date(2032, 9, 26),
        date_fin=date(2033, 6, 19),
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
        "etudiant": profil.pk, "montant": "200", "date_paiement": "2032-10-14",
        "mode": "virement", "statut": "confirme", "cours_session": offres[0].pk,
    })
    assert form.is_valid(), form.errors
    paiement = form.save()
    assert paiement.session == session
    assert paiement.cours_session == offres[0]
    assert all(x.cours_id != annonce.pk for x in form.fields["cours_session"].queryset)


@pytest.mark.django_db
def test_selection_etudiant_recherchable_dans_le_formulaire_de_paiement(client, exemple):
    """Le formulaire de création ET celui de modification exposent le bon sélecteur."""
    agent, profil, session, offres, _ = exemple
    profil.utilisateur.first_name = "Élodie"
    profil.utilisateur.last_name = "Durand"
    profil.utilisateur.save(update_fields=["first_name", "last_name"])

    client.force_login(agent)
    creation = client.get(reverse("administration:payment_create"))
    assert creation.status_code == 200
    contenu = creation.content.decode()
    assert 'data-recherche-etudiant-paiement="1"' in contenu
    assert "Élodie Durand" in contenu
    assert profil.numero_etudiant in contenu

    paiement = Paiement.objects.create(
        etudiant=profil, session=session, cours_session=offres[0],
        date_paiement=date(2032, 10, 14), montant=Decimal("200"),
        mode="virement", statut="confirme",
    )
    modification = client.get(reverse("administration:payment_update", args=[paiement.pk]))
    assert modification.status_code == 200
    assert 'data-recherche-etudiant-paiement="1"' in modification.content.decode()
    assert modification.context["form"]["etudiant"].value() == profil.pk


@pytest.mark.django_db
def test_recherche_ne_remplace_pas_la_validation_du_choix_etudiant(exemple):
    """Seul l'identifiant d'un étudiant existant est accepté par Django."""
    agent, profil, _, _, _ = exemple
    donnees = {
        "montant": "200", "date_paiement": "2032-10-14",
        "mode": "virement", "statut": "confirme",
    }
    valide = PaiementForm(data={**donnees, "etudiant": profil.pk})
    invalide = PaiementForm(data={**donnees, "etudiant": "999999"})
    assert valide.is_valid(), valide.errors
    assert not invalide.is_valid()
    assert "etudiant" in invalide.errors


@pytest.mark.django_db
def test_paiement_atelier_non_reutilisable_pour_un_autre(exemple):
    agent, profil, session, offres, annonce = exemple
    paiement = Paiement.objects.create(
        etudiant=profil, session=session, cours_session=offres[0],
        date_paiement=date(2032, 10, 14), montant=Decimal("200"),
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
        date_paiement=date(2032, 10, 14), montant=Decimal("200"),
        mode="virement", statut="confirme",
    )
    client.force_login(agent)
    liste = client.get(reverse("administration:payments"), {"q": "théologie"})
    assert liste.status_code == 200
    assert paiement in liste.context["paiements"]
    fiche = client.get(reverse("administration:etudiant_detail", args=[profil.pk]))
    assert offres[0].cours.titre in fiche.content.decode()


@pytest.mark.django_db
def test_une_session_permet_de_voir_ses_cours_et_leurs_details(client, exemple):
    agent, profil, session, offres, annonce = exemple
    offres[0].horaires = "Le samedi de 9 h à 12 h"
    offres[0].salle = "Salle de formation"
    offres[0].save(update_fields=["horaires", "salle", "updated_at"])
    client.force_login(agent)

    reponse = client.get(reverse("administration:sessions"))
    assert reponse.status_code == 200
    contenu = reponse.content.decode()
    assert "Cours programmés (2)" in contenu
    assert "Voir les détails de la session" in contenu
    # Un clic sur l'en-tête de la carte ouvre directement les détails natifs.
    assert '<details class="group">' in contenu
    assert '<summary class="cursor-pointer' in contenu
    assert contenu.index('<summary class="cursor-pointer') < contenu.index(session.nom) < contenu.index("</summary>")
    # Les commandes de modification restent distinctes de la zone activable.
    assert contenu.index("</details>") < contenu.index(
        reverse("administration:session_update", args=[session.pk])
    )
    assert offres[0].cours.titre in contenu
    assert offres[1].cours.titre in contenu
    assert "Salle de formation" in contenu
    assert "Le samedi de 9 h à 12 h" in contenu
    assert "Présentiel" in contenu
    assert reverse("administration:course_offering_update", args=[offres[0].pk]) in contenu
    assert f"?session={session.pk}" in contenu
    assert annonce.titre not in contenu


@pytest.mark.django_db
def test_une_session_sans_cours_l_indique(client, exemple):
    agent, _, _, _, _ = exemple
    nouvelle_session = SessionAcademique.objects.create(
        nom="Cycle sans cours",
        periode="formation",
        annee_academique="2032-2033",
        date_debut=date(2033, 1, 11),
        date_fin=date(2033, 1, 12),
    )
    client.force_login(agent)

    reponse = client.get(reverse("administration:sessions"))
    assert reponse.status_code == 200
    contenu = reponse.content.decode()
    assert "Cycle sans cours" in contenu
    assert "Aucun cours ou atelier n’a encore été programmé pour cette session." in contenu
    assert f"?session={nouvelle_session.pk}" in contenu
