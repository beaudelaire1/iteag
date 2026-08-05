"""Rédaction des documents officiels de l'institut.

Le point sensible n'est pas la mise en page mais **la référence**. Un numéro
inscrit au registre désigne un document parti ; s'il désigne autre chose une
semaine plus tard, ou s'il manque un numéro dans la suite, le registre ne vaut
plus rien. Les tests portent donc d'abord sur son attribution, son unicité et
sa conservation.
"""

import json
import re
from unittest.mock import patch

import pytest
from django.core.exceptions import ValidationError
from django.test import override_settings
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


FICHE_CONVOCATION = {
    "date_seance": "2026-09-12",
    "heure_seance": "18:00",
    "lieu": "Salle du conseil, campus des Abymes",
}


@pytest.fixture
def document(secretaire):
    return DocumentRedige.objects.create(
        titre="Convocation du conseil",
        genre=DocumentRedige.Genre.CONVOCATION,
        objet="Séance du conseil pédagogique du 12 septembre",
        corps=[("paragraphe", "<p>Vous êtes convoqué à la séance du conseil.</p>")],
        destinataire_nom="Monsieur le Pasteur Jean Dupont",
        signataire_nom="Alain Nisus",
        signataire_qualite="Directeur",
        donnees=dict(FICHE_CONVOCATION),
        redige_par=secretaire,
    )


def _corps_poste(texte="La rentrée est fixée au 14 septembre.", champ="corps"):
    """Le corps tel que le widget StreamField l'envoie.

    Deux encodages s'emboîtent, et c'est ce qui rend la construction pénible
    mais nécessaire :

    1. le **StreamBlock** poste une série indexée à la manière d'un formset —
       un compteur, puis un type, un ordre et une valeur par bloc ;
    2. la valeur d'un bloc « paragraphe » est un **ContentState** Draftail,
       c'est-à-dire du JSON, et non du HTML.

    Poster « <p>…</p> » échoue donc deux fois : d'abord sur « corps-count »
    manquant, ensuite sur du JSON illisible. Un test qui tombe pour l'une de
    ces raisons n'apprend rien sur ce qu'il prétend vérifier.

    Un texte vide produit un corps sans aucun bloc — la façon correcte de dire
    « brouillon encore vide ».
    """
    if not texte:
        return {f"{champ}-count": "0"}

    contenu = json.dumps(
        {
            "blocks": [
                {
                    "key": "bloc1",
                    "text": texte,
                    "type": "unstyled",
                    "depth": 0,
                    "inlineStyleRanges": [],
                    "entityRanges": [],
                    "data": {},
                }
            ],
            "entityMap": {},
        }
    )
    return {
        f"{champ}-count": "1",
        f"{champ}-0-deleted": "",
        f"{champ}-0-order": "0",
        f"{champ}-0-type": "paragraphe",
        f"{champ}-0-id": "",
        f"{champ}-0-value": contenu,
    }


def _saisie(corps="La rentrée est fixée au 14 septembre.", **surcharges):
    donnees = {
        "titre": "Courrier de rentrée",
        "genre": DocumentRedige.Genre.COURRIER,
        "date_document": "2026-09-14",
        "objet": "Ouverture de l'année académique",
        "destinataire_nom": "",
        "destinataire_adresse": "",
        "signataire_nom": "",
        "signataire_qualite": "",
    }
    donnees.update(_corps_poste(corps))
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
            corps=[("paragraphe", "<p>Texte.</p>")],
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
            corps=[("paragraphe", "<p>Texte.</p>")],
            date_document=document.date_document,
            donnees=dict(FICHE_CONVOCATION),
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
        vide = DocumentRedige.objects.create(titre="Sans objet", objet="   ", corps=[("paragraphe", "<p>Texte.</p>")])
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

    @override_settings(CELERY_TASK_ALWAYS_EAGER=False)
    @patch("apps.documents.tasks.generer_document_redige.apply_async")
    def test_finaliser_lance_le_pdf_en_arriere_plan(self, publier, client, secretaire, document):
        client.force_login(secretaire)

        reponse = client.post(
            reverse("redaction:document_decision", args=[document.pk]),
            {"action": "finaliser"},
        )

        document.refresh_from_db()
        assert reponse.status_code == 302
        assert document.est_finalise
        assert document.statut_generation == document.StatutGeneration.EN_ATTENTE
        assert not document.fichier_pdf
        publier.assert_called_once_with(
            args=(document.pk, str(document.jeton_generation)),
            ignore_result=True,
            retry=False,
        )

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
        finalise = DocumentRedige.objects.create(
            titre="Note déjà partie", objet="Un objet", corps=[("paragraphe", "<p>Texte.</p>")]
        )
        finalise.finaliser(par=secretaire)
        client.force_login(secretaire)

        contenu = client.get(reverse("redaction:documents")).content.decode()
        assert "Brouillons (1)" in contenu
        assert "Finalisés (1)" in contenu

    def test_le_filtre_par_genre_restreint_la_liste(self, client, secretaire, document):
        DocumentRedige.objects.create(
            titre="Un rapport", genre=DocumentRedige.Genre.RAPPORT, objet="Objet", corps=[("paragraphe", "<p>x</p>")]
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

    def test_le_logo_ne_repete_pas_iteag_en_toutes_lettres(self, document):
        html = self._html(document)

        assert html.count('class="iteag-letterhead__logo"') == 1
        assert 'class="iteag-letterhead__fallback"' not in html

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
    @override_settings(DOCUMENTS_PDF_LOCAL_FALLBACK=True)
    @patch("apps.documents.tasks.generer_document_redige.apply_async")
    @patch("apps.documents.tasks.Thread")
    def test_le_telechargement_local_ne_contacte_pas_redis(self, thread, publier, client, secretaire, document):
        client.force_login(secretaire)

        reponse = client.get(reverse("redaction:document_pdf", args=[document.pk]))

        assert reponse.status_code == 302
        publier.assert_not_called()
        thread.assert_called_once()
        thread.return_value.start.assert_called_once_with()

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


# ══════════════════════════════════════════════
# Les fiches propres au genre
# ══════════════════════════════════════════════


class TestFicheDuGenre:
    """Le défaut que ces fiches corrigent : un corps libre pour tous les genres.

    Une convocation porte une date, une heure et un lieu. Dans un modèle plat,
    rien ne le rappelle et rien ne le vérifie : on écrit « venez mardi », le
    document part, et personne ne sait où se rendre. La fiche fait de ces
    champs une exigence, pas un souvenir à avoir.
    """

    def test_une_convocation_sans_lieu_ne_se_finalise_pas(self, document, secretaire):
        document.donnees = {"date_seance": "2026-09-12", "heure_seance": "18:00"}
        document.save()

        with pytest.raises(ValidationError) as echec:
            document.finaliser(par=secretaire)
        assert "lieu" in str(echec.value).lower()

    def test_le_message_nomme_ce_qui_manque(self, document, secretaire):
        """« Document incomplet » n'aide personne à le compléter."""
        document.donnees = {}
        document.save()

        with pytest.raises(ValidationError) as echec:
            document.finaliser(par=secretaire)
        message = str(echec.value).lower()
        for attendu in ("date de la séance", "heure", "lieu"):
            assert attendu in message

    def test_un_courrier_n_exige_aucun_champ_propre(self, secretaire):
        """Tous les genres n'ont pas de fiche : le courrier se suffit de l'objet."""
        courrier = DocumentRedige.objects.create(
            titre="Un courrier",
            genre=DocumentRedige.Genre.COURRIER,
            objet="Objet",
            corps=[("paragraphe", "<p>Texte.</p>")],
        )
        courrier.finaliser(par=secretaire)
        assert courrier.est_finalise

    def test_le_brouillon_accepte_une_fiche_vide(self, client, secretaire):
        """On écrit rarement une convocation d'un seul jet."""
        client.force_login(secretaire)
        client.post(
            f"{reverse('redaction:document_creation')}?genre=convocation",
            _saisie(genre="convocation"),
        )

        cree = DocumentRedige.objects.get(titre="Courrier de rentrée")
        assert cree.genre == "convocation"
        assert cree.est_modifiable

    def test_la_fiche_saisie_est_conservee(self, client, secretaire):
        client.force_login(secretaire)
        client.post(
            f"{reverse('redaction:document_creation')}?genre=convocation",
            _saisie(genre="convocation", **FICHE_CONVOCATION),
        )

        cree = DocumentRedige.objects.get(titre="Courrier de rentrée")
        assert cree.donnees["lieu"] == FICHE_CONVOCATION["lieu"]
        assert str(cree.donnees["date_seance"]) == "2026-09-12"

    def test_le_genre_ne_change_plus_apres_creation(self, client, secretaire, document):
        """Sa fiche déjà remplie n'aurait plus de sens sous un autre genre."""
        client.force_login(secretaire)
        client.post(
            reverse("redaction:document_edition", args=[document.pk]),
            _saisie(genre=DocumentRedige.Genre.RAPPORT),
        )

        document.refresh_from_db()
        assert document.genre == DocumentRedige.Genre.CONVOCATION

    def test_creer_sans_genre_propose_de_choisir(self, client, secretaire):
        """La fiche à remplir dépend du genre : le demander vient donc avant."""
        client.force_login(secretaire)
        contenu = client.get(reverse("redaction:document_creation")).content.decode()

        assert "Quel document" in contenu
        assert "genre=convocation" in contenu

    def test_l_ecran_montre_les_champs_du_genre(self, client, secretaire, document):
        client.force_login(secretaire)
        contenu = client.get(reverse("redaction:document_edition", args=[document.pk])).content.decode()

        assert "Salle du conseil" in contenu
        assert "Heure" in contenu

    def test_le_pdf_porte_les_champs_du_genre(self, document, secretaire):
        from django.template.loader import render_to_string

        from apps.core.services.pdf import contexte_marque

        document.finaliser(par=secretaire)
        html = render_to_string(
            "documents/pdf/document_redige.html",
            contexte_marque(profil_polices="document_administratif", document=document),
        )
        assert "Salle du conseil" in html


class TestFormulaireSansCorps:
    """Un envoi sans corps ne doit pas faire tomber le serveur.

    « MultiValueDictKeyError: 'corps-count' » : un StreamBlock lit cette clé
    sans filet, et la vue rendait un 500 là où elle devait afficher un
    formulaire. La clé manque dès que le widget ne s'est pas amorcé — script
    absent, page envoyée trop tôt, requête forgée.
    """

    def test_un_envoi_sans_le_champ_corps_ne_tombe_pas(self, client, secretaire):
        client.force_login(secretaire)
        donnees = {cle: valeur for cle, valeur in _saisie().items() if not cle.startswith("corps-")}

        reponse = client.post(reverse("redaction:document_creation"), donnees)

        assert reponse.status_code < 500, "Un formulaire incomplet s'affiche, il ne plante pas."
        assert DocumentRedige.objects.filter(titre="Courrier de rentrée").exists()

    def test_le_document_ainsi_créé_reste_un_brouillon_sans_corps(self, client, secretaire):
        client.force_login(secretaire)
        donnees = {cle: valeur for cle, valeur in _saisie().items() if not cle.startswith("corps-")}
        client.post(reverse("redaction:document_creation"), donnees)

        cree = DocumentRedige.objects.get(titre="Courrier de rentrée")
        assert cree.est_modifiable
        with pytest.raises(ValidationError):
            cree.finaliser(par=secretaire)

    def test_la_page_charge_le_script_d_amorcage(self, client, secretaire, document):
        """Sans lui, le champ reste un div et l'envoi repart sans corps."""
        client.force_login(secretaire)
        contenu = client.get(reverse("redaction:document_edition", args=[document.pk])).content.decode()

        assert "streamfield-portail.js" in contenu
        assert 'data-controller="w-block"' in contenu

    def test_le_prefixe_des_champs_vient_de_l_identifiant(self):
        """Le contrat entre le gabarit et le script d'amorçage.

        « data-w-block-arguments-value » ne porte que l'état initial et les
        erreurs — il vaut « [[], null] ». Le préfixe, lui, est l'identifiant de
        l'élément : c'est lui qui donnera « corps-count » et « corps-0-type ».

        L'oublier ne lève aucune erreur : les champs naissent sous des noms
        absurdes et la zone reste visuellement vide. Ce test fige donc les deux
        moitiés du contrat, faute de pouvoir exécuter le script ici.
        """
        import json
        import re
        from html import unescape
        from pathlib import Path

        from django.conf import settings

        from apps.documents.formulaires import DocumentRedigeForm

        rendu = str(DocumentRedigeForm()["corps"])
        assert 'id="corps"' in rendu, "Le préfixe des champs est lu sur l'identifiant."

        arguments = re.search(r'data-w-block-arguments-value="([^"]*)"', rendu)
        assert arguments, "Le widget doit publier ses arguments d'initialisation."
        assert len(json.loads(unescape(arguments.group(1)))) == 2, (
            "Deux arguments seulement : le préfixe doit donc être fourni à part."
        )

        script = (Path(settings.BASE_DIR) / "static" / "js" / "streamfield-portail.js").read_text(encoding="utf-8")
        assert "emplacement.id" in script, "Le script doit passer l'identifiant comme préfixe."


class TestSocleWagtail:
    """Le socle JavaScript conditionne l'existence même du champ.

    Les bundles de Wagtail supposent « vendor.js » déjà chargé. Servis seuls,
    ils s'exécutent sans rien enregistrer : telepath reste vide, le champ ne se
    construit pas, et l'envoi part sans « corps-count ». Mesuré en navigateur —
    zéro adaptateur sans le socle, seize avec.

    Le symptôme est trompeur : un intitulé sans zone de saisie, puis une erreur
    500 côté serveur. Rien ne désigne le socle manquant.
    """

    def test_la_page_sert_le_socle_avant_les_bundles(self, client, secretaire, document):
        client.force_login(secretaire)
        contenu = client.get(reverse("redaction:document_edition", args=[document.pk])).content.decode()

        assert "wagtailadmin/js/vendor.js" in contenu, "Sans « vendor.js », aucun adaptateur ne s'enregistre."
        assert contenu.index("wagtailadmin/js/vendor.js") < contenu.index("telepath/blocks.js"), (
            "Le socle doit précéder les bundles qui en dépendent."
        )

    def test_la_page_sert_la_configuration_wagtail(self, client, secretaire, document):
        """« vendor.js » la lit au démarrage et abandonne si elle manque.

        Sans elle : « Unexpected end of JSON input », puis « window.telepath »
        jamais créé, puis une cascade de « Cannot read properties of undefined
        (reading 'register') » sur tous les bundles. Rien dans ces messages ne
        désigne la configuration absente — d'où trois correctifs à côté avant
        de trouver.
        """
        client.force_login(secretaire)
        contenu = client.get(reverse("redaction:document_edition", args=[document.pk])).content.decode()

        assert 'id="wagtail-config"' in contenu, "« vendor.js » ne démarre pas sans elle."
        assert contenu.index("wagtail-config") < contenu.index("wagtailadmin/js/vendor.js"), (
            "La configuration doit précéder le bundle qui la lit."
        )

    def test_le_bloc_de_configuration_porte_un_nonce(self, client, secretaire, document):
        """« script-src 'self' » bloque aussi les blocs en ligne.

        Y compris de type « application/json ». Sans nonce, le navigateur
        écarte le bloc, « vendor.js » lit une chaîne vide et lève « Unexpected
        end of JSON input » — puis « window.telepath » n'est jamais créé et
        tous les bundles échouent sur « undefined (reading 'register') ».

        Le piège : l'élément **est** dans le HTML servi. Aucune inspection
        côté serveur ne peut voir le blocage ; seule la console du navigateur
        le montre.
        """
        client.force_login(secretaire)
        reponse = client.get(reverse("redaction:document_edition", args=[document.pk]))
        contenu = reponse.content.decode()

        bloc = re.search(r'<script id="wagtail-config"[^>]*>', contenu)
        assert bloc, "La configuration doit être servie."
        assert "nonce=" in bloc.group(0), "Sans nonce, la CSP écarte le bloc et vendor.js abandonne."

        # La CSP est désactivée dans les réglages de test — il n'y a donc aucun
        # en-tête à lire. On vérifie l'autre moitié du contrat là où elle vit :
        # la politique de base doit demander l'insertion du nonce dans
        # « script-src », faute de quoi l'attribut posé sur le bloc n'autorise
        # rien.
        from config.settings import base

        directives = base.CONTENT_SECURITY_POLICY["DIRECTIVES"]
        assert "script-src" in directives.get("include-nonce-in", []), (
            "Sans « include-nonce-in », le nonce du bloc n'est pas repris dans la politique."
        )
