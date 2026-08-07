import pytest
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.accounts.models import User
from apps.admissions.models import DemandePieces, DossierCandidature, PieceDemandee
from apps.core.models import Notification
from apps.formations.models import Parcours


@pytest.fixture
def univers_pieces_groupes(db):
    parcours = Parcours.objects.create(
        nom="Certificat pièces groupées",
        slug="certificat-pieces-groupees",
        type_parcours=Parcours.TypeParcours.DIPLOMANT_ITEAG,
    )
    dossier = DossierCandidature.objects.create(
        nom="Dorival",
        prenom="Anne",
        email="anne.dorival@example.org",
        parcours_souhaite=parcours,
        motivations="Approfondir ma formation.",
        statut=DossierCandidature.Statut.ACCEPTE,
    )
    secretaire = User.objects.create_user(
        username="secretariat_lot",
        email="secretariat-lot@iteag.org",
        password="motdepasse-long-12",
        role=User.Role.SECRETARIAT,
    )
    admin = User.objects.create_user(
        username="admin_lot",
        email="admin-lot@iteag.org",
        password="motdepasse-long-12",
        role=User.Role.ADMIN,
    )
    return dossier, secretaire, admin


def fichier(nom):
    return SimpleUploadedFile(nom, b"%PDF-1.4 contenu", content_type="application/pdf")


@pytest.mark.django_db
def test_message_commun_n_est_present_qu_une_fois(client, univers_pieces_groupes):
    dossier, secretaire, _ = univers_pieces_groupes
    client.force_login(secretaire)
    mail.outbox.clear()

    client.post(
        reverse("administration:demander_pieces", args=[dossier.pk]),
        {
            "pieces": ["Acte de naissance", "Photo d'identité"],
            "piece_libre": "",
            "precisions": "Merci de transmettre des copies lisibles.",
        },
    )

    demande = DemandePieces.objects.get(dossier=dossier)
    assert demande.pieces.count() == 2
    assert demande.message == "Merci de transmettre des copies lisibles."
    assert len(mail.outbox) == 1
    assert mail.outbox[0].body.count("Merci de transmettre des copies lisibles.") == 1


@pytest.mark.django_db
def test_candidat_depose_tout_le_lot_et_admin_recoit_une_notification(client, univers_pieces_groupes):
    dossier, secretaire, admin = univers_pieces_groupes
    client.force_login(secretaire)
    client.post(
        reverse("administration:demander_pieces", args=[dossier.pk]),
        {"pieces": ["Acte de naissance", "Photo d'identité"], "piece_libre": "", "precisions": ""},
    )
    client.logout()
    demande = DemandePieces.objects.prefetch_related("pieces").get(dossier=dossier)
    pieces = list(demande.pieces.order_by("pk"))
    mail.outbox.clear()
    Notification.objects.all().delete()

    reponse = client.post(
        reverse("admissions:deposer_piece", args=[dossier.token_suivi, demande.pk]),
        {
            f"piece_{pieces[0].pk}": fichier("acte.pdf"),
            f"piece_{pieces[1].pk}": fichier("photo.pdf"),
        },
    )

    assert reponse.status_code == 302
    demande.refresh_from_db()
    assert demande.statut == DemandePieces.Statut.A_VERIFIER
    assert not demande.pieces.exclude(statut=PieceDemandee.Statut.DEPOSEE).exists()
    assert len(mail.outbox) == 1
    assert Notification.objects.filter(destinataire=admin, titre__startswith="Documents déposés").count() == 1
    assert Notification.objects.filter(destinataire=secretaire, titre__startswith="Documents déposés").count() == 1


@pytest.mark.django_db
def test_secretariat_prend_une_decision_groupee_et_un_seul_mail_part(client, univers_pieces_groupes):
    dossier, secretaire, _ = univers_pieces_groupes
    demande = DemandePieces.objects.create(dossier=dossier, demandee_par=secretaire)
    acte = PieceDemandee.objects.create(
        dossier=dossier,
        demande=demande,
        libelle="Acte de naissance",
        demandee_par=secretaire,
    )
    photo = PieceDemandee.objects.create(
        dossier=dossier,
        demande=demande,
        libelle="Photo d'identité",
        demandee_par=secretaire,
    )
    acte.deposer(fichier("acte.pdf"))
    photo.deposer(fichier("photo.pdf"))
    demande.marquer_deposee()
    client.force_login(secretaire)
    mail.outbox.clear()

    reponse = client.post(
        reverse("administration:piece_decision", args=[demande.pk]),
        {
            f"decision_{acte.pk}": "valider",
            f"motif_{acte.pk}": "",
            f"decision_{photo.pk}": "refuser",
            f"motif_{photo.pk}": "La photo est trop sombre.",
        },
    )

    assert reponse.status_code == 302
    acte.refresh_from_db()
    photo.refresh_from_db()
    demande.refresh_from_db()
    assert acte.statut == PieceDemandee.Statut.VALIDEE
    assert photo.statut == PieceDemandee.Statut.REFUSEE
    assert demande.statut == DemandePieces.Statut.A_CORRIGER
    assert len(mail.outbox) == 1
    assert "Acte de naissance" in mail.outbox[0].body
    assert "La photo est trop sombre." in mail.outbox[0].body
