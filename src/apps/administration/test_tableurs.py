"""Import et export des fichiers du secrétariat.

Le point qui décide de tout est l'atomicité : un import à moitié appliqué
laisse un fichier dont plus personne ne sait quelle moitié est à jour. Une
seule ligne fautive doit donc annuler l'ensemble, et le rapport doit lister
toutes les erreurs d'un coup — sans quoi le fichier se redépose autant de fois
qu'il compte de fautes.

Les pièges reproduits ici viennent tous du terrain : Excel écrit des CSV au
point-virgule, les préfixe d'une marque d'ordre d'octets, et relit un code
numérique en flottant.
"""

import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.academics.models import ProfilEtudiant, Promotion
from apps.accounts.models import User
from apps.administration.services.tableurs import SCHEMAS
from apps.core.services import tableur
from apps.core.services.import_tableur import executer
from apps.formations.models import Cours, Discipline, Parcours, Professeur
from apps.library.models import NoticeBibliographique

pytestmark = pytest.mark.django_db

MOT_DE_PASSE = "motdepasse-long-12"


@pytest.fixture
def secretaire(db):
    return User.objects.create_user(
        username="sec_tab", email="st@iteag.org", password=MOT_DE_PASSE, role=User.Role.SECRETARIAT
    )


@pytest.fixture
def referentiel(db):
    discipline = Discipline.objects.create(nom="Théologie", slug="theo-tab")
    parcours = Parcours.objects.create(
        nom="Licence en théologie", slug="lic-tab", type_parcours=Parcours.TypeParcours.LIBRE
    )
    promotion = Promotion.objects.create(nom="Promotion 2026", parcours=parcours, annee_debut=2026, annee_fin=2029)
    return discipline, parcours, promotion


def _fichier(nom: str, contenu: bytes) -> SimpleUploadedFile:
    return SimpleUploadedFile(nom, contenu, content_type="text/csv")


def _csv(entetes: list[str], lignes: list[list[str]], separateur=";", bom=True) -> bytes:
    corps = separateur.join(entetes) + "\n"
    corps += "\n".join(separateur.join(ligne) for ligne in lignes)
    return corps.encode("utf-8-sig" if bom else "utf-8")


# ══════════════════════════════════════════════
# Le moteur de lecture
# ══════════════════════════════════════════════


class TestLectureDesFichiers:
    def test_le_point_virgule_d_excel_est_reconnu(self):
        """Lu avec des virgules, ce fichier donnerait une colonne par ligne."""
        donnees = tableur.lire(_fichier("f.csv", _csv(["nom", "prenom"], [["Nisus", "Alain"]])))
        assert donnees == [{"nom": "Nisus", "prenom": "Alain"}]

    def test_la_virgule_reste_reconnue(self):
        donnees = tableur.lire(_fichier("f.csv", _csv(["nom", "prenom"], [["Nisus", "Alain"]], separateur=",")))
        assert donnees == [{"nom": "Nisus", "prenom": "Alain"}]

    def test_la_marque_d_ordre_d_octets_ne_casse_pas_la_premiere_colonne(self):
        """Sans « utf-8-sig », la première en-tête devient « ﻿nom » et paraît absente."""
        donnees = tableur.lire(_fichier("f.csv", _csv(["nom", "prenom"], [["Nisus", "Alain"]], bom=True)))
        assert "nom" in donnees[0]

    def test_les_entetes_tolerent_la_casse_et_les_espaces(self):
        donnees = tableur.lire(_fichier("f.csv", _csv([" Nom ", "PRENOM"], [["Nisus", "Alain"]])))
        assert donnees[0]["nom"] == "Nisus"
        assert donnees[0]["prenom"] == "Alain"

    def test_un_code_numerique_ne_revient_pas_en_flottant(self):
        """Excel relit « 2026001 » en float : la comparaison échouerait en silence."""
        classeur = tableur.ecrire_xlsx("x.xlsx", ["numero_etudiant"], [[2026001]])
        donnees = tableur.lire(SimpleUploadedFile("x.xlsx", classeur.content))
        assert donnees[0]["numero_etudiant"] == "2026001"

    def test_un_fichier_vide_est_refuse_clairement(self):
        with pytest.raises(tableur.FichierIllisible):
            tableur.lire(_fichier("f.csv", b""))


# ══════════════════════════════════════════════
# L'atomicité
# ══════════════════════════════════════════════


class TestToutOuRien:
    def test_une_ligne_fautive_annule_tout_l_import(self, referentiel):
        """C'est l'invariant : jamais de fichier à moitié à jour."""
        contenu = _csv(
            ["nom", "prenom", "disciplines"],
            [
                ["Nisus", "Alain", "Théologie"],
                ["Toussaint", "Gérard", "Discipline qui n'existe pas"],
                ["Céleste", "Patrick", "Théologie"],
            ],
        )
        rapport = executer(SCHEMAS["professeurs"], _fichier("p.csv", contenu))

        assert rapport.est_en_echec
        assert Professeur.objects.count() == 0, "Aucune ligne ne doit subsister"

    def test_toutes_les_erreurs_sont_rapportees_d_un_coup(self, referentiel):
        contenu = _csv(
            ["nom", "prenom", "disciplines"],
            [
                ["Nisus", "Alain", "Inconnue A"],
                ["Toussaint", "Gérard", "Inconnue B"],
            ],
        )
        rapport = executer(SCHEMAS["professeurs"], _fichier("p.csv", contenu))

        assert len(rapport.erreurs) == 2, "S'arrêter à la première ferait redéposer le fichier dix fois"

    def test_le_numero_de_ligne_est_celui_qu_excel_affiche(self, referentiel):
        """« ligne 3 » doit désigner la troisième ligne à l'écran, en-tête comprise."""
        contenu = _csv(
            ["nom", "prenom", "disciplines"],
            [["Nisus", "Alain", "Théologie"], ["Toussaint", "Gérard", "Inconnue"]],
        )
        rapport = executer(SCHEMAS["professeurs"], _fichier("p.csv", contenu))

        assert rapport.erreurs[0][0] == 3

    def test_une_colonne_obligatoire_absente_arrete_avant_toute_ecriture(self, referentiel):
        rapport = executer(SCHEMAS["professeurs"], _fichier("p.csv", _csv(["prenom"], [["Alain"]])))
        assert rapport.est_en_echec
        assert "nom" in rapport.erreurs[0][1]
        assert Professeur.objects.count() == 0

    def test_les_lignes_vides_d_excel_sont_ignorees(self, referentiel):
        """Excel produit des milliers de lignes blanches en fin de feuille."""
        contenu = _csv(["nom", "prenom"], [["Nisus", "Alain"], ["", ""], ["", ""]])
        rapport = executer(SCHEMAS["professeurs"], _fichier("p.csv", contenu))

        assert not rapport.est_en_echec
        assert rapport.crees == 1
        assert rapport.ignores == 2


# ══════════════════════════════════════════════
# Les clés naturelles
# ══════════════════════════════════════════════


class TestMiseAJourSansDoublon:
    def test_reimporter_met_a_jour_au_lieu_de_dupliquer(self, referentiel):
        contenu = _csv(["nom", "prenom", "specialite"], [["Nisus", "Alain", "Dogmatique"]])
        executer(SCHEMAS["professeurs"], _fichier("p.csv", contenu))

        corrige = _csv(["nom", "prenom", "specialite"], [["Nisus", "Alain", "Théologie systématique"]])
        rapport = executer(SCHEMAS["professeurs"], _fichier("p.csv", corrige))

        assert Professeur.objects.count() == 1
        assert rapport.mis_a_jour == 1 and rapport.crees == 0
        assert Professeur.objects.get().specialite == "Théologie systématique"

    def test_l_etudiant_est_reconnu_par_son_numero(self, referentiel):
        _, parcours, promotion = referentiel
        entetes = ["numero_etudiant", "nom", "prenom", "email", "parcours", "promotion"]
        ligne = ["ETU2026001", "Marceline", "Josiane", "josiane@example.org", parcours.nom, promotion.nom]

        executer(SCHEMAS["etudiants"], _fichier("e.csv", _csv(entetes, [ligne])))
        rapport = executer(SCHEMAS["etudiants"], _fichier("e.csv", _csv(entetes, [ligne])))

        assert ProfilEtudiant.objects.count() == 1
        assert rapport.mis_a_jour == 1

    def test_le_numero_absent_est_attribue(self, referentiel):
        """
        Le secrétariat reprend des listes qui ne portent aucun numéro.

        Exiger une colonne que le fichier d'origine ignore obligeait à inventer
        des numéros à la main avant tout import — le numéro se génère déjà seul
        à l'acceptation d'une candidature.
        """
        _, parcours, promotion = referentiel
        contenu = _csv(
            ["nom", "prenom", "email", "parcours", "promotion"],
            [["Marceline", "Josiane", "josiane@example.org", parcours.nom, promotion.nom]],
        )
        rapport = executer(SCHEMAS["etudiants"], _fichier("e.csv", contenu))

        assert not rapport.est_en_echec
        assert rapport.crees == 1
        assert ProfilEtudiant.objects.get().numero_etudiant.startswith("ETU")

    def test_deux_lignes_sans_numero_ne_se_marchent_pas_dessus(self, referentiel):
        _, parcours, promotion = referentiel
        contenu = _csv(
            ["nom", "prenom", "email", "parcours", "promotion"],
            [
                ["Marceline", "Josiane", "josiane@example.org", parcours.nom, promotion.nom],
                ["Sainte-Rose", "Emmanuel", "emmanuel@example.org", parcours.nom, promotion.nom],
            ],
        )
        executer(SCHEMAS["etudiants"], _fichier("e.csv", contenu))

        numeros = set(ProfilEtudiant.objects.values_list("numero_etudiant", flat=True))
        assert len(numeros) == 2

    def test_sans_numero_l_email_fait_cle(self, referentiel):
        """Sans clé de repli, redéposer le même fichier créerait tout en double."""
        _, parcours, promotion = referentiel
        entetes = ["nom", "prenom", "email", "parcours", "promotion"]
        ligne = ["Marceline", "Josiane", "josiane@example.org", parcours.nom, promotion.nom]

        executer(SCHEMAS["etudiants"], _fichier("e.csv", _csv(entetes, [ligne])))
        rapport = executer(SCHEMAS["etudiants"], _fichier("e.csv", _csv(entetes, [ligne])))

        assert ProfilEtudiant.objects.count() == 1
        assert rapport.mis_a_jour == 1

    def test_le_rattachement_pedagogique_peut_manquer(self, referentiel):
        """
        Reprendre un effectif existant, c'est importer des noms et des emails.

        Le parcours et la promotion exacts se renseignent ensuite, sur la fiche.
        Les exiger au dépôt obligeait à les retrouver avant tout import.
        """
        contenu = _csv(
            ["nom", "prenom", "email"],
            [["Marceline", "Josiane", "josiane@example.org"]],
        )
        rapport = executer(SCHEMAS["etudiants"], _fichier("e.csv", contenu))

        assert not rapport.est_en_echec
        profil = ProfilEtudiant.objects.get()
        assert profil.parcours_id is None
        assert profil.promotion_id is None

    def test_une_colonne_vide_ne_detache_pas_un_etudiant_rattache(self, referentiel):
        """Un second dépôt partiel ne doit rien défaire de ce qui est en place."""
        _, parcours, promotion = referentiel
        complet = _csv(
            ["nom", "prenom", "email", "parcours", "promotion"],
            [["Marceline", "Josiane", "josiane@example.org", parcours.nom, promotion.nom]],
        )
        executer(SCHEMAS["etudiants"], _fichier("e.csv", complet))

        partiel = _csv(["nom", "prenom", "email"], [["Marceline", "Josiane", "josiane@example.org"]])
        executer(SCHEMAS["etudiants"], _fichier("e.csv", partiel))

        profil = ProfilEtudiant.objects.get()
        assert profil.parcours_id == parcours.pk
        assert profil.promotion_id == promotion.pk

    def test_un_parcours_inconnu_reste_refuse(self, referentiel):
        """Vide est permis ; mal orthographié ne l'est pas."""
        contenu = _csv(
            ["nom", "prenom", "email", "parcours"],
            [["Marceline", "Josiane", "josiane@example.org", "Licence en théologi"]],
        )
        rapport = executer(SCHEMAS["etudiants"], _fichier("e.csv", contenu))

        assert rapport.est_en_echec
        assert "Parcours inconnu" in rapport.erreurs[0][1]
        assert ProfilEtudiant.objects.count() == 0

    def test_l_email_est_desormais_exige(self, referentiel):
        """Sans lui, le compte créé serait injoignable pour définir son mot de passe."""
        _, parcours, promotion = referentiel
        contenu = _csv(
            ["numero_etudiant", "nom", "prenom", "parcours", "promotion"],
            [["ETU2026009", "Marceline", "Josiane", parcours.nom, promotion.nom]],
        )
        rapport = executer(SCHEMAS["etudiants"], _fichier("e.csv", contenu))

        assert rapport.est_en_echec
        assert "email" in rapport.erreurs[0][1]

    def test_sans_numero_ni_email_la_ligne_est_refusee(self, referentiel):
        """Ni l'un ni l'autre : plus rien ne distingue cette personne d'une nouvelle."""
        _, parcours, promotion = referentiel
        contenu = _csv(
            ["nom", "prenom", "parcours", "promotion"],
            [["Marceline", "Josiane", parcours.nom, promotion.nom]],
        )
        rapport = executer(SCHEMAS["etudiants"], _fichier("e.csv", contenu))

        assert rapport.est_en_echec
        assert "email" in rapport.erreurs[0][1]
        assert ProfilEtudiant.objects.count() == 0

    def test_le_compte_importe_n_a_pas_de_mot_de_passe_utilisable(self, referentiel):
        """Un import ne fabrique pas de mot de passe et n'en fait transiter aucun."""
        _, parcours, promotion = referentiel
        contenu = _csv(
            ["numero_etudiant", "nom", "prenom", "email", "parcours", "promotion"],
            [["ETU2026002", "Sainte-Rose", "Emmanuel", "emmanuel@example.org", parcours.nom, promotion.nom]],
        )
        executer(SCHEMAS["etudiants"], _fichier("e.csv", contenu))

        profil = ProfilEtudiant.objects.get()
        assert profil.utilisateur.has_usable_password() is False

    def test_la_notice_est_reconnue_par_son_isbn(self, referentiel):
        entetes = ["titre", "auteur", "isbn"]
        executer(SCHEMAS["bibliotheque"], _fichier("b.csv", _csv(entetes, [["Théologie", "Berkhof", "978200"]])))
        executer(
            SCHEMAS["bibliotheque"],
            _fichier("b.csv", _csv(entetes, [["Théologie systématique", "Berkhof", "978200"]])),
        )

        assert NoticeBibliographique.objects.count() == 1
        assert NoticeBibliographique.objects.get().titre == "Théologie systématique"

    def test_un_cours_est_reconnu_par_son_code(self, referentiel):
        discipline, _, _ = referentiel
        entetes = ["code", "titre", "discipline", "ects"]
        executer(
            SCHEMAS["cours"], _fichier("c.csv", _csv(entetes, [["THEO-101", "Herméneutique", discipline.nom, "5"]]))
        )
        executer(
            SCHEMAS["cours"],
            _fichier("c.csv", _csv(entetes, [["THEO-101", "Herméneutique biblique", discipline.nom, "6"]])),
        )

        assert Cours.objects.count() == 1
        cours = Cours.objects.get()
        assert cours.titre == "Herméneutique biblique"
        assert str(cours.ects) == "6.0" or cours.ects == 6


# ══════════════════════════════════════════════
# Les écrans
# ══════════════════════════════════════════════


class TestEcrans:
    def test_le_secretariat_ouvre_la_liste(self, client, secretaire):
        client.force_login(secretaire)
        reponse = client.get(reverse("administration:tableurs"))
        assert reponse.status_code == 200
        assert "Corps enseignant" in reponse.content.decode()

    def test_le_gabarit_excel_se_telecharge_avec_ses_entetes(self, client, secretaire):
        client.force_login(secretaire)
        reponse = client.get(reverse("administration:tableur_gabarit", args=["professeurs", "xlsx"]))

        assert reponse.status_code == 200
        assert "attachment" in reponse["Content-Disposition"]
        donnees = tableur.lire(SimpleUploadedFile("g.xlsx", reponse.content))
        assert "nom" in donnees[0], "Le gabarit doit porter ses en-têtes et une ligne d'exemple"

    def test_l_export_reprend_les_donnees(self, client, secretaire, referentiel):
        Professeur.objects.create(nom="Nisus", prenom="Alain", slug="nisus-export")
        client.force_login(secretaire)

        reponse = client.get(reverse("administration:tableur_export", args=["professeurs", "csv"]))

        assert reponse.status_code == 200
        assert "Nisus" in reponse.content.decode("utf-8-sig")

    def test_l_export_neutralise_les_formules(self, client, secretaire, referentiel):
        """Un nom commençant par « = » s'exécuterait à l'ouverture du tableur."""
        Professeur.objects.create(nom="=SOMME(A1:A9)", prenom="Piégé", slug="piege-export")
        client.force_login(secretaire)

        contenu = client.get(reverse("administration:tableur_export", args=["professeurs", "csv"])).content.decode(
            "utf-8-sig"
        )
        assert "'=SOMME" in contenu

    def test_l_import_par_l_ecran_rend_compte(self, client, secretaire, referentiel):
        client.force_login(secretaire)
        contenu = _csv(["nom", "prenom"], [["Nisus", "Alain"]])

        reponse = client.post(
            reverse("administration:tableur_import", args=["professeurs"]),
            {"fichier": _fichier("p.csv", contenu)},
            follow=True,
        )

        assert reponse.status_code == 200
        assert Professeur.objects.count() == 1
        assert any("création" in str(m) for m in reponse.context["messages"])

    def test_un_import_fautif_affiche_le_detail_des_lignes(self, client, secretaire, referentiel):
        client.force_login(secretaire)
        contenu = _csv(["nom", "prenom", "disciplines"], [["Nisus", "Alain", "Inconnue"]])

        reponse = client.post(
            reverse("administration:tableur_import", args=["professeurs"]),
            {"fichier": _fichier("p.csv", contenu)},
        )

        assert reponse.status_code == 200
        page = reponse.content.decode()
        assert "rien n&#x27;a été enregistré" in page or "rien n'a été enregistré" in page
        assert "Discipline inconnue" in page

    def test_un_jeu_de_donnees_inconnu_repond_404(self, client, secretaire):
        client.force_login(secretaire)
        assert client.get(reverse("administration:tableur_detail", args=["inexistant"])).status_code == 404

    def test_un_etudiant_n_accede_ni_a_l_export_ni_a_l_import(self, client, db):
        intrus = User.objects.create_user(
            username="intrus_tab", email="it@iteag.org", password=MOT_DE_PASSE, role=User.Role.ETUDIANT
        )
        client.force_login(intrus)

        assert client.get(reverse("administration:tableurs")).status_code in (302, 403)
        assert client.get(reverse("administration:tableur_export", args=["etudiants", "csv"])).status_code in (302, 403)
        assert client.post(
            reverse("administration:tableur_import", args=["etudiants"]),
            {"fichier": _fichier("e.csv", b"nom\n")},
        ).status_code in (302, 403)


def test_ecrire_xlsx_produit_un_classeur_relisible():
    reponse = tableur.ecrire_xlsx("t.xlsx", ["a", "b"], [["1", "2"]])
    from openpyxl import load_workbook

    classeur = load_workbook(io.BytesIO(reponse.content))
    assert [cellule.value for cellule in classeur.active[1]] == ["a", "b"]
