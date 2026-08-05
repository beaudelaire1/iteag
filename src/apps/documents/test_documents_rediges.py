"""Rédaction des documents officiels de l'institut.

Le point sensible n'est pas la mise en page mais **la référence**. Un numéro
inscrit au registre désigne un document parti ; s'il désigne autre chose une
semaine plus tard, ou s'il manque un numéro dans la suite, le registre ne vaut
plus rien. Les tests portent donc d'abord sur son attribution, son unicité et
sa conservation.
"""

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse

from apps.accounts.models import User
from apps.core.models import JournalAudit
from apps.documents.models import DocumentRedige

pytestmark = pytest.mark.django_db

MOT_DE_PASSE = "motdepasse-long-12"


@pytest.fixture
def secretaire(db):
    return User.objects.create_user(
        username="sec_doc", email="sd@iteag.org", password=MOT_DE_PASSE, role=User.Role.SECRETARIAT
    )


@pytest.fixture
def directrice(db):
    return User.objects.create_user(
        username="dir_doc", email="dd@iteag.org", password=MOT_DE_PASSE, role=User.Role.ADMIN
    )


@pytest.fixture
def document(secretaire):
    return DocumentRedige.objects.create(
        titre="Convocation du conseil",
        genre=DocumentRedige.Genre.CONVOCATION,
        objet="Séance du conseil pédagogique du 12 septembre",
        corps="<p>Vous êtes convoqué à la séance du conseil.</p>",
        destinataire_nom="Monsieur le Pasteur Jean Dupont",
        signataire_nom="Alain Nisus",
        signataire_qualite="Directeur",
        redige_par=secretaire,
    )


def _saisie(**surcharges):
    donnees = {
        "titre": "Courrier de rentrée",
        "genre": DocumentRedige.Genre.COURRIER,
        "date_document": "2026-09-14",
        "objet": "Ouverture de l'année académique",
        "destinataire_nom": "",
        "destinataire_adresse": "",
        "corps": "<p>La rentrée est fixée au 14 septembre.</p>",
        "signataire_nom": "",
        "signataire_qualite": "",
    }
    donnees.update(surcharges)
    return donnees


# ══════════════════════════════════════════════
# La référence
# ══════════════════════════════════════════════


class TestReference:
    def test_un_brouillon_ne_consomme_pas_de_numero(self, document):
        """Sinon on cherche des années le courrier qui n'a jamais existé."""
        assert not document.reference

    def test_la_finalisation_attribue_la_reference(self, document, secretaire):
        document.finaliser(par=secretaire)
        annee = document.date_document.year
        assert document.reference == f"ITEAG/CVN/{annee}/001"

    def test_le_compteur_est_propre_au_genre(self, secretaire, document):
        document.finaliser(par=secretaire)
        courrier = DocumentRedige.objects.create(
            titre="Un courrier",
            genre=DocumentRedige.Genre.COURRIER,
            objet="Objet",
            corps="<p>Texte.</p>",
            date_document=document.date_document,
        )
        courrier.finaliser(par=secretaire)

        annee = document.date_document.year
        assert courrier.reference == f"ITEAG/COU/{annee}/001"

    def test_le_compteur_avance_dans_le_meme_genre(self, secretaire, document):
        document.finaliser(par=secretaire)
        suivante = DocumentRedige.objects.create(
            titre="Seconde convocation",
            genre=DocumentRedige.Genre.CONVOCATION,
            objet="Objet",
            corps="<p>Texte.</p>",
            date_document=document.date_document,
        )
        suivante.finaliser(par=secretaire)

        annee = document.date_document.year
        assert suivante.reference == f"ITEAG/CVN/{annee}/002"

    def test_la_reference_est_conservee_apres_reouverture(self, document, secretaire):
        """Un numéro délivré reste délivré, même si le texte est repris."""
        document.finaliser(par=secretaire)
        reference = document.reference

        document.revenir_en_brouillon()
        document.finaliser(par=secretaire)

        assert document.reference == reference


# ══════════════════════════════════════════════
# Le cycle de vie
# ══════════════════════════════════════════════


class TestCycle:
    def test_un_document_naît_en_brouillon(self, document):
        assert document.est_modifiable
        assert not document.est_finalise

    def test_finaliser_sans_corps_est_refuse(self, secretaire):
        vide = DocumentRedige.objects.create(titre="Sans corps", objet="Un objet", corps="")
        with pytest.raises(ValidationError):
            vide.finaliser(par=secretaire)

    def test_finaliser_sans_objet_est_refuse(self, secretaire):
        vide = DocumentRedige.objects.create(titre="Sans objet", objet="   ", corps="<p>Texte.</p>")
        with pytest.raises(ValidationError):
            vide.finaliser(par=secretaire)

    def test_un_document_finalise_n_est_plus_modifiable(self, document, secretaire):
        document.finaliser(par=secretaire)
        assert not document.est_modifiable

    def test_on_ne_finalise_pas_deux_fois(self, document, secretaire):
        document.finaliser(par=secretaire)
        with pytest.raises(ValidationError):
            document.finaliser(par=secretaire)

    def test_rouvrir_un_brouillon_est_refuse(self, document):
        with pytest.raises(ValidationError):
            document.revenir_en_brouillon()

    def test_la_reouverture_rouvre_la_redaction(self, document, secretaire):
        document.finaliser(par=secretaire)
        document.revenir_en_brouillon()

        assert document.est_modifiable
        assert document.date_finalisation is None


# ══════════════════════════════════════════════
# Les écrans
# ══════════════════════════════════════════════


class TestPerimetre:
    def test_le_secretariat_redige(self, client, secretaire):
        client.force_login(secretaire)
        assert client.get(reverse("redaction:documents")).status_code == 200

    def test_la_direction_aussi(self, client, directrice):
        client.force_login(directrice)
        assert client.get(reverse("redaction:documents")).status_code == 200

    def test_un_enseignant_n_y_accede_pas(self, client, db):
        prof = User.objects.create_user(
            username="prof_doc", email="pd@iteag.org", password=MOT_DE_PASSE, role=User.Role.ENSEIGNANT
        )
        client.force_login(prof)
        assert client.get(reverse("redaction:documents")).status_code in (302, 403)

    def test_un_etudiant_n_y_accede_pas(self, client, db):
        etudiant = User.objects.create_user(
            username="etu_doc", email="ed@iteag.org", password=MOT_DE_PASSE, role=User.Role.ETUDIANT
        )
        client.force_login(etudiant)
        assert client.get(reverse("redaction:documents")).status_code in (302, 403)

    def test_la_barre_du_secretariat_y_mene(self, client, secretaire):
        """Un droit sans chemin pour l'exercer n'existe pas dans les faits."""
        client.force_login(secretaire)
        barre = client.get(reverse("secretariat:dashboard")).content.decode()
        assert f'href="{reverse("redaction:documents")}"' in barre

    def test_la_barre_de_la_direction_y_mene(self, client, directrice):
        client.force_login(directrice)
        barre = client.get(reverse("administration:dashboard")).content.decode()
        assert f'href="{reverse("redaction:documents")}"' in barre


class TestRedaction:
    def test_ecrire_un_document(self, client, secretaire):
        client.force_login(secretaire)
        client.post(reverse("redaction:document_creation"), _saisie())

        cree = DocumentRedige.objects.get(titre="Courrier de rentrée")
        assert cree.est_modifiable
        assert cree.redige_par == secretaire

    def test_un_document_sans_objet_est_refuse(self, client, secretaire):
        client.force_login(secretaire)
        reponse = client.post(reverse("redaction:document_creation"), _saisie(objet=""))

        assert reponse.status_code == 200
        assert not DocumentRedige.objects.filter(titre="Courrier de rentrée").exists()

    def test_un_brouillon_accepte_un_corps_vide(self, client, secretaire):
        """On écrit rarement un courrier d'un seul jet."""
        client.force_login(secretaire)
        client.post(reverse("redaction:document_creation"), _saisie(corps=""))

        assert DocumentRedige.objects.filter(titre="Courrier de rentrée").exists()

    def test_un_document_finalise_ne_se_modifie_pas_par_l_ecran(self, client, secretaire, document):
        document.finaliser(par=secretaire)
        client.force_login(secretaire)

        client.post(
            reverse("redaction:document_edition", args=[document.pk]),
            _saisie(titre="Titre remplacé"),
        )

        document.refresh_from_db()
        assert document.titre == "Convocation du conseil"

    def test_l_ecriture_laisse_une_trace(self, client, secretaire):
        client.force_login(secretaire)
        client.post(reverse("redaction:document_creation"), _saisie())

        assert JournalAudit.objects.filter(action=JournalAudit.Action.CREATION, objet_type="DocumentRedige").exists()


class TestDecisions:
    def test_finaliser_depuis_l_ecran(self, client, secretaire, document):
        client.force_login(secretaire)
        client.post(reverse("redaction:document_decision", args=[document.pk]), {"action": "finaliser"})

        document.refresh_from_db()
        assert document.est_finalise
        assert document.reference

    def test_un_document_finalise_ne_se_supprime_pas(self, client, secretaire, document):
        """Le détruire laisserait un trou dans le registre."""
        document.finaliser(par=secretaire)
        client.force_login(secretaire)

        client.post(reverse("redaction:document_decision", args=[document.pk]), {"action": "supprimer"})

        assert DocumentRedige.objects.filter(pk=document.pk).exists()

    def test_un_brouillon_se_supprime(self, client, secretaire, document):
        client.force_login(secretaire)
        client.post(reverse("redaction:document_decision", args=[document.pk]), {"action": "supprimer"})

        assert not DocumentRedige.objects.filter(pk=document.pk).exists()

    def test_rouvrir_depuis_l_ecran(self, client, secretaire, document):
        document.finaliser(par=secretaire)
        client.force_login(secretaire)

        client.post(reverse("redaction:document_decision", args=[document.pk]), {"action": "rouvrir"})

        document.refresh_from_db()
        assert document.est_modifiable

    def test_une_action_inconnue_ne_change_rien(self, client, secretaire, document):
        client.force_login(secretaire)
        client.post(reverse("redaction:document_decision", args=[document.pk]), {"action": "n_importe_quoi"})

        document.refresh_from_db()
        assert document.est_modifiable
        assert DocumentRedige.objects.filter(pk=document.pk).exists()


class TestListe:
    def test_les_brouillons_et_les_finalises_sont_separes(self, client, secretaire, document):
        finalise = DocumentRedige.objects.create(titre="Note déjà partie", objet="Un objet", corps="<p>Texte.</p>")
        finalise.finaliser(par=secretaire)
        client.force_login(secretaire)

        contenu = client.get(reverse("redaction:documents")).content.decode()
        assert "Brouillons (1)" in contenu
        assert "Finalisés (1)" in contenu

    def test_le_filtre_par_genre_restreint_la_liste(self, client, secretaire, document):
        DocumentRedige.objects.create(
            titre="Un rapport", genre=DocumentRedige.Genre.RAPPORT, objet="Objet", corps="<p>x</p>"
        )
        client.force_login(secretaire)

        contenu = client.get(reverse("redaction:documents"), {"genre": DocumentRedige.Genre.RAPPORT}).content.decode()
        assert "Un rapport" in contenu
        assert "Convocation du conseil" not in contenu

    def test_un_genre_inconnu_ne_vide_pas_la_liste(self, client, secretaire, document):
        """Une adresse bricolée à la main ne doit pas faire croire à un registre vide."""
        client.force_login(secretaire)

        contenu = client.get(reverse("redaction:documents"), {"genre": "inexistant"}).content.decode()
        assert "Convocation du conseil" in contenu


# ══════════════════════════════════════════════
# Le PDF
# ══════════════════════════════════════════════


class TestGabaritPdf:
    """Le gabarit est vérifié en HTML, avant WeasyPrint.

    Rendre un PDF pour y chercher une chaîne coûte des secondes et ne dit rien
    de précis en cas d'échec. Le gabarit, lui, se rend en millisecondes et se
    lit. Le PDF n'est éprouvé qu'une fois, pour prouver que la chaîne complète
    tient debout.
    """

    def _html(self, document):
        from django.template.loader import render_to_string

        from apps.core.services.pdf import contexte_marque

        return render_to_string(
            "documents/pdf/document_redige.html",
            contexte_marque(profil_polices="document_administratif", document=document),
        )

    def test_le_document_finalise_porte_sa_reference(self, document, secretaire):
        document.finaliser(par=secretaire)
        html = self._html(document)

        assert document.reference in html
        assert "Séance du conseil pédagogique" in html
        assert "Monsieur le Pasteur Jean Dupont" in html
        assert "Alain Nisus" in html

    def test_le_brouillon_porte_un_filigrane(self, document):
        """Une impression posée sur un bureau ne doit pas passer pour une pièce arrêtée."""
        html = self._html(document)

        assert "BROUILLON" in html
        assert "Sans référence" in html

    def test_le_filigrane_disparaît_une_fois_finalise(self, document, secretaire):
        document.finaliser(par=secretaire)
        assert "BROUILLON" not in self._html(document)

    def test_le_corps_riche_est_rendu(self, document):
        """« richtext » convertit le format de stockage de Wagtail."""
        assert "Vous êtes convoqué" in self._html(document)


class TestChainePdf:
    def test_la_finalisation_archive_un_vrai_pdf(self, client, secretaire, document, settings, tmp_path):
        settings.MEDIA_ROOT = tmp_path
        client.force_login(secretaire)

        client.post(reverse("redaction:document_decision", args=[document.pk]), {"action": "finaliser"})

        document.refresh_from_db()
        assert document.fichier_pdf, "Le PDF doit être archivé à la finalisation."
        assert document.fichier_pdf.open("rb").read(5) == b"%PDF-"

    def test_la_reouverture_jette_le_pdf(self, client, secretaire, document, settings, tmp_path):
        """Il décrirait un texte qui n'est plus celui du document."""
        settings.MEDIA_ROOT = tmp_path
        client.force_login(secretaire)
        client.post(reverse("redaction:document_decision", args=[document.pk]), {"action": "finaliser"})
        client.post(reverse("redaction:document_decision", args=[document.pk]), {"action": "rouvrir"})

        document.refresh_from_db()
        assert not document.fichier_pdf
