from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
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
from apps.academics.services.inscriptions import soumettre_demande, traiter_demande
from apps.accounts.models import User
from apps.core.models import Notification
from apps.formations.models import Cours, Discipline, Parcours, Professeur


@pytest.fixture
def enrollment_context(db):
    parcours = Parcours.objects.create(
        nom="Parcours diplômant",
        slug="parcours-demandes",
        type_parcours=Parcours.TypeParcours.DIPLOMANT_ITEAG,
    )
    promotion = Promotion.objects.create(
        nom="Promotion demandes",
        parcours=parcours,
        annee_debut=2026,
        annee_fin=2032,
    )
    utilisateur = User.objects.create_user(
        username="etudiant-demandes",
        password="motdepasse-solide-123",
        email="etudiant-demandes@iteag.org",
        first_name="Anne",
        last_name="Durand",
        role=User.Role.ETUDIANT,
    )
    etudiant = ProfilEtudiant.objects.create(
        utilisateur=utilisateur,
        parcours=parcours,
        promotion=promotion,
        numero_etudiant="ETU-DEMANDES",
        statut_inscription=ProfilEtudiant.StatutInscription.ACTIF,
    )
    discipline = Discipline.objects.create(nom="Nouveau Testament demandes", slug="nt-demandes")
    cours = Cours.objects.create(
        titre="Lecture de l'Évangile",
        slug="lecture-evangile-demandes",
        discipline=discipline,
        description="Cours complet pour tester le catalogue.",
    )
    cours.parcours.add(parcours)
    professeur = Professeur.objects.create(nom="Martin", prenom="Jeanne", slug="jeanne-martin-demandes")
    session = SessionAcademique.objects.create(
        nom="Session demandes",
        periode=SessionAcademique.Periode.JUILLET,
        annee_academique="2026-2027",
        date_debut=timezone.localdate() + timedelta(days=10),
        date_fin=timezone.localdate() + timedelta(days=17),
    )
    offre = CoursDeSession.objects.create(
        session=session,
        cours=cours,
        enseignant=professeur,
        capacite=2,
        frais_inscription=Decimal("120.00"),
        date_limite_inscription=timezone.localdate() + timedelta(days=8),
    )
    secretariat = User.objects.create_user(
        username="secretariat-demandes",
        password="motdepasse-solide-123",
        role=User.Role.SECRETARIAT,
    )
    return {
        "etudiant": etudiant,
        "offre": offre,
        "session": session,
        "secretariat": secretariat,
    }


@pytest.mark.django_db
class TestStudentEnrollmentJourney:
    def test_catalogue_displays_eligible_course(self, client, enrollment_context):
        client.force_login(enrollment_context["etudiant"].utilisateur)
        response = client.get(reverse("etudiant:course_catalogue"))
        assert response.status_code == 200
        assert enrollment_context["offre"].pk in {offre.pk for offre in response.context["offres"]}

    def test_student_submits_and_cancels_request(self, client, enrollment_context):
        etudiant = enrollment_context["etudiant"]
        offre = enrollment_context["offre"]
        client.force_login(etudiant.utilisateur)

        response = client.post(
            reverse("etudiant:enrollment_request_create", kwargs={"pk": offre.pk}),
            {"note_etudiant": "Je souhaite suivre cette session."},
        )
        assert response.status_code == 302
        demande = DemandeInscriptionCours.objects.get(etudiant=etudiant, cours_session=offre)
        assert demande.statut == DemandeInscriptionCours.Statut.SOUMISE
        assert demande.montant_du == Decimal("120.00")
        assert demande.historique.count() == 1
        # Les titres portent désormais le cours concerné : on vérifie que
        # l'avis part et qu'il nomme sa demande, sans figer la formulation.
        assert Notification.objects.filter(
            destinataire=etudiant.utilisateur,
            titre__startswith="Demande d'inscription enregistrée",
            titre__contains=offre.cours.titre,
        ).exists()
        assert Notification.objects.filter(
            destinataire=enrollment_context["secretariat"],
            titre__startswith="Nouvelle demande d'inscription",
            titre__contains=offre.cours.titre,
        ).exists()

        response = client.post(reverse("etudiant:enrollment_request_cancel", kwargs={"pk": demande.pk}))
        assert response.status_code == 302
        demande.refresh_from_db()
        assert demande.statut == DemandeInscriptionCours.Statut.ANNULEE
        assert demande.historique.count() == 2
        assert Notification.objects.filter(
            destinataire=etudiant.utilisateur,
            titre__startswith="Demande d'inscription annulée",
            titre__contains=offre.cours.titre,
        ).exists()

    def test_student_payment_and_request_tracking_pages(self, client, enrollment_context):
        client.force_login(enrollment_context["etudiant"].utilisateur)
        assert client.get(reverse("etudiant:enrollment_requests")).status_code == 200
        assert client.get(reverse("etudiant:payments")).status_code == 200

    def test_duplicate_pending_request_is_not_created(self, client, enrollment_context):
        etudiant = enrollment_context["etudiant"]
        offre = enrollment_context["offre"]
        client.force_login(etudiant.utilisateur)
        url = reverse("etudiant:enrollment_request_create", kwargs={"pk": offre.pk})
        client.post(url, {})
        client.post(url, {})
        assert DemandeInscriptionCours.objects.filter(etudiant=etudiant, cours_session=offre).count() == 1


@pytest.mark.django_db
class TestEnrollmentDecisionWorkflow:
    def test_payment_is_required_before_confirmation(self, enrollment_context):
        demande = soumettre_demande(
            etudiant=enrollment_context["etudiant"],
            cours_session=enrollment_context["offre"],
        )
        with pytest.raises(ValidationError, match="paiement confirmé"):
            traiter_demande(
                demande=demande,
                action="confirmer",
                par=enrollment_context["secretariat"],
            )
        assert not InscriptionSession.objects.filter(demande=demande).exists()

    def test_confirmed_payment_creates_course_enrollment(self, enrollment_context):
        etudiant = enrollment_context["etudiant"]
        demande = soumettre_demande(etudiant=etudiant, cours_session=enrollment_context["offre"])
        paiement = Paiement.objects.create(
            etudiant=etudiant,
            session=enrollment_context["session"],
            montant=Decimal("120.00"),
            date_paiement=timezone.localdate(),
            mode=Paiement.ModePaiement.VIREMENT,
            statut=Paiement.StatutPaiement.CONFIRME,
            reference="VIR-ITEAG-001",
        )
        traiter_demande(
            demande=demande,
            action="confirmer",
            par=enrollment_context["secretariat"],
            paiement=paiement,
            commentaire="Paiement contrôlé.",
        )
        demande.refresh_from_db()
        assert demande.statut == DemandeInscriptionCours.Statut.CONFIRMEE
        assert demande.paiement == paiement
        assert InscriptionSession.objects.filter(
            etudiant=etudiant,
            cours_session=enrollment_context["offre"],
            demande=demande,
        ).exists()

    def test_capacity_is_checked_inside_confirmation(self, enrollment_context):
        offre = enrollment_context["offre"]
        offre.capacite = 1
        offre.save(update_fields=["capacite"])
        autre_user = User.objects.create_user(username="autre-capacite", role=User.Role.ETUDIANT)
        autre = ProfilEtudiant.objects.create(
            utilisateur=autre_user,
            parcours=enrollment_context["etudiant"].parcours,
            promotion=enrollment_context["etudiant"].promotion,
            numero_etudiant="ETU-CAPACITE",
            statut_inscription=ProfilEtudiant.StatutInscription.ACTIF,
        )
        InscriptionSession.objects.create(etudiant=autre, cours_session=offre)
        demande = DemandeInscriptionCours.objects.create(
            etudiant=enrollment_context["etudiant"],
            cours_session=offre,
            montant_du=0,
        )
        with pytest.raises(ValidationError, match="complet"):
            traiter_demande(
                demande=demande,
                action="confirmer",
                par=enrollment_context["secretariat"],
                exonere_paiement=True,
                commentaire="Test de capacité.",
            )

    def test_secretariat_can_process_but_student_cannot_open_staff_queue(self, client, enrollment_context):
        demande = soumettre_demande(
            etudiant=enrollment_context["etudiant"],
            cours_session=enrollment_context["offre"],
        )
        client.force_login(enrollment_context["secretariat"])
        response = client.get(reverse("administration:enrollment_request_detail", kwargs={"pk": demande.pk}))
        assert response.status_code == 200

        client.force_login(enrollment_context["etudiant"].utilisateur)
        response = client.get(reverse("administration:enrollment_requests"))
        assert response.status_code == 403

    def test_secretariat_operational_crud_screens(self, client, enrollment_context):
        client.force_login(enrollment_context["secretariat"])
        assert client.get(reverse("administration:course_offerings")).status_code == 200
        assert client.get(reverse("administration:course_offering_create")).status_code == 200
        assert client.get(reverse("administration:payments")).status_code == 200
        assert client.get(reverse("administration:payment_create")).status_code == 200
        assert client.get(reverse("administration:session_create")).status_code == 200

    def test_un_nouveau_cours_disponible_previent_les_etudiants(self, client, enrollment_context):
        offre = enrollment_context["offre"]
        etudiant = enrollment_context["etudiant"]
        cours = Cours.objects.create(
            titre="Cours nouvellement disponible",
            slug="cours-nouvellement-disponible",
            discipline=offre.cours.discipline,
        )
        cours.parcours.add(etudiant.parcours)
        client.force_login(enrollment_context["secretariat"])

        reponse = client.post(
            reverse("administration:course_offering_create"),
            {
                "session": offre.session_id,
                "cours": cours.pk,
                "enseignant": offre.enseignant_id,
                "modalite": CoursDeSession.Modalite.PRESENTIEL,
                "salle": "",
                "horaires": "",
                "statut": CoursDeSession.StatutCours.PROGRAMME,
                "capacite": 30,
                "inscriptions_ouvertes": "on",
                "date_limite_inscription": "",
                "frais_inscription": "0",
                "informations_pratiques": "",
            },
        )

        assert reponse.status_code == 302
        assert Notification.objects.filter(
            destinataire=etudiant.utilisateur,
            titre="Cours disponible — Cours nouvellement disponible",
        ).exists()

    def test_un_paiement_enregistre_previent_l_etudiant(self, client, enrollment_context):
        etudiant = enrollment_context["etudiant"]
        client.force_login(enrollment_context["secretariat"])

        reponse = client.post(
            reverse("administration:payment_create"),
            {
                "etudiant": etudiant.pk,
                "session": enrollment_context["session"].pk,
                "montant": "120.00",
                "date_paiement": timezone.localdate().isoformat(),
                "mode": Paiement.ModePaiement.VIREMENT,
                "statut": Paiement.StatutPaiement.CONFIRME,
                "reference": "TEST-NOTIFICATION",
            },
        )

        assert reponse.status_code == 302
        assert Notification.objects.filter(destinataire=etudiant.utilisateur, titre="Paiement enregistré").exists()
