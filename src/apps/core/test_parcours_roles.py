"""Parcours complets, espace par espace : ce qu'une personne fait vraiment.

Les autres fichiers vérifient des vues prises une à une. Celui-ci suit le
chemin : on se connecte, on regarde la barre, on clique sur ce qu'elle propose,
on fait l'acte, et on vérifie qu'il a produit son effet là où l'utilisateur
l'attend — sur le site public, dans sa liste, sur son tableau de bord.

C'est le seul niveau où se voient les défauts qui ont motivé ce fichier, et
qu'aucun test unitaire n'attrapait :

- une entrée de barre affichée **deux fois**, parce qu'un gabarit partagé
  ajoutait sa fin à une barre déjà complète ;
- un écran atteignable depuis la barre d'un rôle **qui n'a pas le droit** de
  l'ouvrir ;
- un acte annoncé par un bouton mais qu'aucune route n'exécutait ;
- un acte proposé quel que soit l'état de l'objet, et refusé une fois sur deux.
"""

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone
from wagtail.models import Site

from apps.academics.models import CoursDeSession, ProfilEtudiant, Promotion, SessionAcademique
from apps.accounts.models import User
from apps.formations.models import Cours, Discipline, Parcours, Professeur
from apps.website.models import NewsIndexPage, NewsPage
from apps.website.models_publications import Article

pytestmark = pytest.mark.django_db

MOT_DE_PASSE = "motdepasse-long-12"


def _lien(route: str, *args) -> str:
    """L'attribut complet : « /espace-admin/ » préfixe la moitié des adresses."""
    return f'href="{reverse(route, args=args)}"'


@pytest.fixture
def index_actualites(db):
    accueil = Site.objects.get(is_default_site=True).root_page
    page = NewsIndexPage(title="Actualités", slug="actualites-parcours")
    accueil.add_child(instance=page)
    return page


@pytest.fixture
def secretaire(db):
    return User.objects.create_user(
        username="sec_parcours", email="sp@iteag.org", password=MOT_DE_PASSE, role=User.Role.SECRETARIAT
    )


@pytest.fixture
def directrice(db):
    return User.objects.create_user(
        username="dir_parcours", email="dp@iteag.org", password=MOT_DE_PASSE, role=User.Role.ADMIN
    )


@pytest.fixture
def enseignant(db):
    compte = User.objects.create_user(
        username="prof_parcours", email="pp@iteag.org", password=MOT_DE_PASSE, role=User.Role.ENSEIGNANT
    )
    return Professeur.objects.create(nom="Nisus", prenom="Alain", slug="nisus-parcours", user=compte)


@pytest.fixture
def etudiante(db, enseignant):
    """Une étudiante, et **un cours ouvert à son parcours**.

    Sans ce cours, l'alerte du tableau de bord ne s'affiche pas du tout et le
    test qui l'examine passerait à côté de son objet sans rien signaler.
    """
    compte = User.objects.create_user(
        username="etu_parcours", email="ep@iteag.org", password=MOT_DE_PASSE, role=User.Role.ETUDIANT
    )
    parcours = Parcours.objects.create(
        nom="Licence", slug="licence-parcours", type_parcours=Parcours.TypeParcours.DIPLOMANT_ITEAG
    )
    ProfilEtudiant.objects.create(
        utilisateur=compte,
        parcours=parcours,
        promotion=Promotion.objects.create(
            nom="Promotion 2026", parcours=parcours, annee_debut=2026, annee_fin=2032
        ),
        numero_etudiant="ETU-PARCOURS-1",
        statut_inscription=ProfilEtudiant.StatutInscription.ACTIF,
    )

    aujourdhui = timezone.localdate()
    session = SessionAcademique.objects.create(
        nom="Session 2026",
        date_debut=aujourdhui - timedelta(days=10),
        date_fin=aujourdhui + timedelta(days=90),
    )
    cours = Cours.objects.create(
        titre="Introduction à l'exégèse",
        slug="intro-exegese-parcours",
        discipline=Discipline.objects.create(nom="Exégèse", slug="exegese-parcours"),
        actif=True,
    )
    cours.parcours.add(parcours)
    CoursDeSession.objects.create(
        cours=cours,
        session=session,
        enseignant=enseignant,
        inscriptions_ouvertes=True,
        statut=CoursDeSession.StatutCours.PROGRAMME,
    )
    return compte


# ══════════════════════════════════════════════
# Secrétariat
# ══════════════════════════════════════════════


class TestParcoursSecretariat:
    def test_la_barre_n_affiche_chaque_entree_qu_une_fois(self, client, secretaire):
        """Le défaut : « Articles », « Imports » et « Mon profil » paraissaient
        deux fois, le gabarit de la direction ajoutant sa fin à une barre du
        secrétariat déjà complète. Deux fois le même lien, sous deux intitulés
        de groupe différents, se lit comme deux écrans distincts.

        Deux occurrences attendues, et pas une de plus : la barre latérale et
        le menu mobile, qui coexistent dans la même page.
        """
        client.force_login(secretaire)
        page = client.get(reverse("secretariat:dashboard")).content.decode()

        for route in ("administration:tableurs", "accounts:profil", "administration:utilisateurs"):
            assert page.count(_lien(route)) == 2, (
                f"{route} paraît {page.count(_lien(route))} fois : "
                "la barre latérale et le menu mobile, pas davantage."
            )

    def test_la_barre_ne_mene_pas_a_la_relecture_des_articles(self, client, secretaire):
        client.force_login(secretaire)
        page = client.get(reverse("secretariat:dashboard")).content.decode()
        assert _lien("website:articles_relecture") not in page

    def test_ecrire_et_publier_une_actualite_depuis_sa_barre(
        self, client, secretaire, index_actualites
    ):
        """Le parcours entier : la barre y mène, l'écran s'ouvre, l'annonce
        s'écrit, se publie, et paraît sur le site public."""
        client.force_login(secretaire)

        barre = client.get(reverse("secretariat:dashboard")).content.decode()
        assert _lien("website:actualites_gestion") in barre

        gestion = client.get(reverse("website:actualites_gestion"))
        assert gestion.status_code == 200
        assert _lien("website:actualite_creation") in gestion.content.decode()

        client.post(
            reverse("website:actualite_creation"),
            {
                "titre": "Journée portes ouvertes",
                "date": "2026-09-14",
                "chapeau": "L'institut ouvre ses portes.",
                "corps": "<p>Venez nous rencontrer le 14 septembre.</p>",
            },
        )
        annonce = NewsPage.objects.get(title="Journée portes ouvertes")
        assert not annonce.live, "Une annonce s'écrit avant de paraître."

        client.post(reverse("website:actualite_decision", args=[annonce.pk]), {"action": "publier"})
        annonce.refresh_from_db()
        assert annonce.live

        client.logout()
        public = client.get(index_actualites.url).content.decode()
        assert "Journée portes ouvertes" in public


# ══════════════════════════════════════════════
# Direction
# ══════════════════════════════════════════════


class TestParcoursDirection:
    def test_la_barre_mene_aux_deux_ecrans_de_publication(self, client, directrice):
        client.force_login(directrice)
        page = client.get(reverse("administration:dashboard")).content.decode()

        assert _lien("website:actualites_gestion") in page
        assert _lien("website:articles_relecture") in page

    def test_ecrire_et_publier_une_actualite(self, client, directrice, index_actualites):
        client.force_login(directrice)
        client.post(
            reverse("website:actualite_creation"),
            {
                "titre": "Soutenance de mémoire",
                "date": "2026-06-20",
                "chapeau": "",
                "corps": "<p>La soutenance est publique.</p>",
            },
        )
        annonce = NewsPage.objects.get(title="Soutenance de mémoire")
        client.post(reverse("website:actualite_decision", args=[annonce.pk]), {"action": "publier"})

        annonce.refresh_from_db()
        assert annonce.live

    def test_relire_un_article_et_le_publier(self, client, directrice, enseignant):
        article = Article.objects.create(
            titre="La christologie de Chalcédoine", auteur=enseignant, corps="<p>Un texte.</p>"
        )
        article.soumettre()
        client.force_login(directrice)

        ecran = client.get(reverse("website:articles_relecture")).content.decode()
        assert "La christologie de Chalcédoine" in ecran

        client.post(reverse("website:article_decision", args=[article.pk]), {"action": "publier"})
        article.refresh_from_db()
        assert article.est_public


# ══════════════════════════════════════════════
# Enseignant
# ══════════════════════════════════════════════


class TestParcoursEnseignant:
    """Chaque état d'un article ouvre les actions qui lui correspondent, et
    elles seules. Un bouton offert quel que soit l'état échouerait une fois
    sur deux sans rien apprendre de ce qui est permis."""

    def _articles_dans_tous_les_etats(self, enseignant, relecteur):
        brouillon = Article.objects.create(titre="Brouillon", auteur=enseignant, corps="<p>x</p>")
        soumis = Article.objects.create(titre="Soumis", auteur=enseignant, corps="<p>x</p>")
        soumis.soumettre()
        publie = Article.objects.create(titre="Publié", auteur=enseignant, corps="<p>x</p>")
        publie.soumettre()
        publie.publier(par=relecteur)
        retire = Article.objects.create(titre="Retiré", auteur=enseignant, corps="<p>x</p>")
        retire.soumettre()
        retire.publier(par=relecteur)
        retire.retirer(par=relecteur)
        return {"brouillon": brouillon, "soumis": soumis, "publié": publie, "retiré": retire}

    def test_la_liste_propose_les_actions_de_chaque_etat(self, client, enseignant, directrice):
        articles = self._articles_dans_tous_les_etats(enseignant, directrice)
        client.force_login(enseignant.user)
        liste = client.get(reverse("website:mes_articles")).content.decode()

        # Supprimable : ce qui n'est lu que par son auteur.
        for etat in ("brouillon", "retiré"):
            assert _lien("website:article_supprimer", articles[etat].pk).replace("href", "action") in liste
        # Pas supprimable : une décision est en cours, ou la page est en ligne.
        for etat in ("soumis", "publié"):
            assert (
                _lien("website:article_supprimer", articles[etat].pk).replace("href", "action")
                not in liste
            )
        # Le retrait ne se demande que pour ce qui est en ligne.
        assert (
            _lien("website:article_demande_retrait", articles["publié"].pk).replace("href", "action")
            in liste
        )
        assert (
            _lien("website:article_demande_retrait", articles["brouillon"].pk).replace("href", "action")
            not in liste
        )

    def test_soumettre_un_article_retire_depuis_sa_liste(self, client, enseignant, directrice):
        articles = self._articles_dans_tous_les_etats(enseignant, directrice)
        client.force_login(enseignant.user)

        liste = client.get(reverse("website:mes_articles")).content.decode()
        assert _lien("website:article_soumettre", articles["retiré"].pk).replace("href", "action") in liste

        client.post(reverse("website:article_soumettre", args=[articles["retiré"].pk]))
        articles["retiré"].refresh_from_db()
        assert articles["retiré"].statut == Article.Statut.RELECTURE

    def test_demander_le_retrait_puis_supprimer_une_fois_accorde(
        self, client, enseignant, directrice
    ):
        """Le parcours complet d'un article qu'on veut faire disparaître :
        il ne se supprime qu'après être redescendu, et l'auteur ne le fait pas
        redescendre lui-même."""
        article = Article.objects.create(titre="À retirer", auteur=enseignant, corps="<p>x</p>")
        article.soumettre()
        article.publier(par=directrice)

        client.force_login(enseignant.user)
        client.post(reverse("website:article_supprimer", args=[article.pk]))
        assert Article.objects.filter(pk=article.pk).exists(), "Une page en ligne ne se supprime pas."

        client.post(
            reverse("website:article_demande_retrait", args=[article.pk]),
            {"motif": "Une source s'est révélée fausse."},
        )
        article.refresh_from_db()
        assert article.retrait_demande and article.est_public

        client.force_login(directrice)
        client.post(reverse("website:article_decision", args=[article.pk]), {"action": "retirer"})

        client.force_login(enseignant.user)
        client.post(reverse("website:article_supprimer", args=[article.pk]))
        assert not Article.objects.filter(pk=article.pk).exists()


# ══════════════════════════════════════════════
# Étudiant
# ══════════════════════════════════════════════


class TestParcoursEtudiant:
    def test_l_annonce_des_cours_est_une_alerte_que_l_on_peut_ecarter(self, client, etudiante):
        """Un bandeau qu'on ne peut pas écarter occupe le haut de l'écran à
        chaque visite, et finit par ne plus être lu.

        Le nombre annoncé est porté par l'alerte : l'écarter mémorise ce
        nombre, et elle reparaît dès qu'un cours de plus est ouvert.
        """
        client.force_login(etudiante)
        tableau = client.get(reverse("etudiant:dashboard")).content.decode()

        assert "cours disponible" in tableau, "Le cours ouvert au parcours doit être annoncé."
        assert 'data-alerte-effacable="catalogue-etudiant"' in tableau
        assert "data-alerte-fermer" in tableau, "Sans bouton, l'alerte est un bandeau figé."
        assert 'data-alerte-valeur="1"' in tableau, (
            "L'alerte porte le nombre annoncé : l'écarter mémorise ce nombre, "
            "et elle reparaît dès qu'un cours de plus est ouvert."
        )

    def test_l_espace_etudiant_ne_mene_a_aucun_ecran_de_publication(self, client, etudiante):
        client.force_login(etudiante)
        tableau = client.get(reverse("etudiant:dashboard")).content.decode()

        assert _lien("website:actualites_gestion") not in tableau
        assert _lien("website:articles_relecture") not in tableau
        assert client.get(reverse("website:actualites_gestion")).status_code in (302, 403)
