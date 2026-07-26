"""
Tests de l'import du catalogue bibliothèque.

L'export de l'ITEAG n'est pas connu à l'avance : ces tests vérifient surtout
que la commande s'adapte aux formes courantes d'un fichier bureautique plutôt
que d'exiger un gabarit exact.
"""

from io import StringIO

import pytest
from django.core.management import CommandError, call_command

from apps.formations.models import Discipline
from apps.library.models import NoticeBibliographique


def ecrire(tmp_path, contenu: str, nom="catalogue.csv", encodage="utf-8"):
    chemin = tmp_path / nom
    chemin.write_text(contenu, encoding=encodage)
    return str(chemin)


def importer(chemin, **options):
    sortie = StringIO()
    call_command("importer_notices", chemin, stdout=sortie, stderr=sortie, **options)
    return sortie.getvalue()


@pytest.mark.django_db
class TestFormatsAcceptes:
    def test_virgule(self, tmp_path):
        chemin = ecrire(tmp_path, "titre,auteur,cote\nInstitution chrétienne,Calvin,BT-100\n")
        importer(chemin)
        notice = NoticeBibliographique.objects.get()
        assert notice.titre == "Institution chrétienne"
        assert notice.auteur == "Calvin"
        assert notice.cote == "BT-100"

    def test_point_virgule(self, tmp_path):
        """Séparateur produit par Excel en configuration française."""
        chemin = ecrire(tmp_path, "titre;auteur;cote\nDogmatique;Barth;BT-200\n")
        importer(chemin)
        assert NoticeBibliographique.objects.get().auteur == "Barth"

    def test_tabulation(self, tmp_path):
        chemin = ecrire(tmp_path, "titre\tauteur\nLa Bible\tCollectif\n")
        importer(chemin)
        assert NoticeBibliographique.objects.count() == 1

    def test_encodage_windows(self, tmp_path):
        """Un export Excel non converti reste lisible."""
        chemin = ecrire(tmp_path, "titre;auteur\nThéologie systématique;Bavinck\n", encodage="cp1252")
        importer(chemin)
        assert NoticeBibliographique.objects.get().titre == "Théologie systématique"

    def test_bom_utf8(self, tmp_path):
        chemin = ecrire(tmp_path, "﻿titre,auteur\nCommentaire,Luther\n")
        importer(chemin)
        assert NoticeBibliographique.objects.get().titre == "Commentaire"


@pytest.mark.django_db
class TestReconnaissanceDesEntetes:
    @pytest.mark.parametrize(
        "entete",
        ["titre", "Titre", "TITRE", "intitulé", "Ouvrage", "title"],
    )
    def test_variantes_du_titre(self, tmp_path, entete):
        chemin = ecrire(tmp_path, f"{entete},auteur\nUn livre,Un auteur\n")
        importer(chemin)
        assert NoticeBibliographique.objects.get().titre == "Un livre"

    def test_variantes_des_autres_champs(self, tmp_path):
        chemin = ecrire(
            tmp_path,
            "Titre;Auteurs;Éditeur;Année;Mots-clés;Cotation;Résumé\n"
            "Éthique;Bonhoeffer;Labor et Fides;1949;éthique, morale;BT-300;Un classique\n",
        )
        importer(chemin)
        notice = NoticeBibliographique.objects.get()
        assert notice.auteur == "Bonhoeffer"
        assert notice.editeur == "Labor et Fides"
        assert notice.date_publication == "1949"
        assert notice.cote == "BT-300"
        assert notice.description == "Un classique"
        assert "éthique" in notice.mots_cles_list

    def test_sans_colonne_de_titre_l_import_est_refuse(self, tmp_path):
        chemin = ecrire(tmp_path, "colonne1,colonne2\nvaleur,valeur\n")
        with pytest.raises(CommandError, match="titre"):
            importer(chemin)

    def test_le_message_d_erreur_liste_les_entetes_trouves(self, tmp_path):
        chemin = ecrire(tmp_path, "machin,truc\na,b\n")
        with pytest.raises(CommandError, match="machin"):
            importer(chemin)


@pytest.mark.django_db
class TestRobustesse:
    def test_les_lignes_sans_titre_sont_ignorees(self, tmp_path):
        chemin = ecrire(tmp_path, "titre,auteur\nUn livre,A\n,B\n  ,C\nAutre livre,D\n")
        sortie = importer(chemin)
        assert NoticeBibliographique.objects.count() == 2
        assert "2 ligne(s) sans titre" in sortie

    def test_les_champs_trop_longs_sont_tronques(self, tmp_path):
        chemin = ecrire(tmp_path, f"titre,auteur\n{'A' * 900},{'B' * 500}\n")
        importer(chemin)
        notice = NoticeBibliographique.objects.get()
        assert len(notice.titre) == 500
        assert len(notice.auteur) == 300

    def test_fichier_introuvable(self, tmp_path):
        with pytest.raises(CommandError, match="introuvable"):
            importer(str(tmp_path / "absent.csv"))

    def test_un_gros_volume_passe(self, tmp_path):
        """L'ITEAG annonce plus de 2 600 notices."""
        lignes = "\n".join(f"Ouvrage {i},Auteur {i},COTE-{i}" for i in range(2635))
        chemin = ecrire(tmp_path, f"titre,auteur,cote\n{lignes}\n")
        importer(chemin)
        assert NoticeBibliographique.objects.count() == 2635


@pytest.mark.django_db
class TestDisciplines:
    def test_rattachement_a_une_discipline_existante(self, tmp_path):
        discipline = Discipline.objects.create(nom="Ancien Testament", slug="ancien-testament")
        chemin = ecrire(tmp_path, "titre,discipline\nGenèse commentée,Ancien Testament\n")
        importer(chemin)
        assert NoticeBibliographique.objects.get().discipline == discipline

    def test_la_correspondance_ignore_la_casse(self, tmp_path):
        discipline = Discipline.objects.create(nom="Ancien Testament", slug="ancien-testament")
        chemin = ecrire(tmp_path, "titre,discipline\nUn livre,ANCIEN TESTAMENT\n")
        importer(chemin)
        assert NoticeBibliographique.objects.get().discipline == discipline

    def test_une_discipline_inconnue_est_creee(self, tmp_path):
        chemin = ecrire(tmp_path, "titre,discipline\nUn livre,Patristique\n")
        importer(chemin)
        assert Discipline.objects.filter(nom="Patristique").exists()

    def test_une_discipline_n_est_creee_qu_une_fois(self, tmp_path):
        chemin = ecrire(tmp_path, "titre,discipline\nA,Patristique\nB,Patristique\nC,Patristique\n")
        importer(chemin)
        assert Discipline.objects.filter(nom="Patristique").count() == 1


@pytest.mark.django_db
class TestOptions:
    def test_la_simulation_n_ecrit_rien(self, tmp_path):
        chemin = ecrire(tmp_path, "titre,auteur\nUn livre,Un auteur\n")
        sortie = importer(chemin, simulation=True)
        assert NoticeBibliographique.objects.count() == 0
        assert "aucune écriture" in sortie.lower()

    def test_la_simulation_annonce_ce_qui_serait_importe(self, tmp_path):
        chemin = ecrire(tmp_path, "titre\nA\nB\nC\n")
        assert "3 notice(s) importée(s)" in importer(chemin, simulation=True)

    def test_l_option_vider_remplace_le_catalogue(self, tmp_path):
        NoticeBibliographique.objects.create(titre="Ancienne notice")
        chemin = ecrire(tmp_path, "titre\nNouvelle notice\n")
        importer(chemin, vider=True)
        assert NoticeBibliographique.objects.count() == 1
        assert NoticeBibliographique.objects.get().titre == "Nouvelle notice"

    def test_sans_vider_l_import_s_ajoute(self, tmp_path):
        NoticeBibliographique.objects.create(titre="Ancienne notice")
        chemin = ecrire(tmp_path, "titre\nNouvelle notice\n")
        importer(chemin)
        assert NoticeBibliographique.objects.count() == 2

    def test_separateur_impose(self, tmp_path):
        chemin = ecrire(tmp_path, "titre|auteur\nUn livre|Un auteur\n")
        importer(chemin, separateur="|")
        assert NoticeBibliographique.objects.get().auteur == "Un auteur"
