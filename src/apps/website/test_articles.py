"""Articles de recherche — rédaction, relecture, lecture publique.

Le point le plus sensible n'est pas le confort de rédaction mais **ce qui entre
en base** : un enseignant compose dans un éditeur visuel, donc le navigateur
envoie du balisage, et ce balisage finit sur une page publique servie sous le
nom de l'institut. Sans liste blanche, un compte compromis — ou une simple
copie depuis un site tiers — suffirait à y injecter du script.

L'assainissement a lieu à l'enregistrement, jamais à l'affichage : ce qui est
en base est déjà propre, et une page qui oublierait un filtre ne deviendrait
pas pour autant vulnérable. Les tests portent donc sur le modèle, pas sur le
gabarit.
"""

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.accounts.models import User
from apps.core.models import Notification
from apps.formations.models import Professeur
from apps.website.models_publications import Article

pytestmark = pytest.mark.django_db

MOT_DE_PASSE = "motdepasse-long-12"


def _png_minimal() -> bytes:
    """Une vraie image : « ImageField » ouvre le fichier pour le valider."""
    import io

    from PIL import Image

    tampon = io.BytesIO()
    Image.new("RGB", (4, 4), "white").save(tampon, format="PNG")
    return tampon.getvalue()


@pytest.fixture
def enseignant(db):
    compte = User.objects.create_user(
        username="prof_art", email="pa@iteag.org", password=MOT_DE_PASSE, role=User.Role.ENSEIGNANT
    )
    return Professeur.objects.create(nom="Nisus", prenom="Alain", slug="nisus-art", user=compte)


@pytest.fixture
def relecteur(db):
    return User.objects.create_user(
        username="sec_art", email="sa@iteag.org", password=MOT_DE_PASSE, role=User.Role.SECRETARIAT
    )


@pytest.fixture
def article(enseignant):
    return Article.objects.create(
        titre="L'ecclésiologie des Pastorales",
        sous_titre="Ce que Paul dit de l'organisation de l'Église",
        auteur=enseignant,
        corps="<p>Un premier paragraphe.</p>",
    )


# ══════════════════════════════════════════════
# Assainissement — le point qui compte
# ══════════════════════════════════════════════


class TestAssainissement:
    def test_le_script_est_retire_a_l_enregistrement(self, enseignant):
        article = Article.objects.create(
            titre="Piégé",
            auteur=enseignant,
            corps='<p>Bonjour</p><script>fetch("/vol")</script>',
        )
        article.refresh_from_db()
        assert "<script" not in article.corps
        assert "Bonjour" in article.corps

    def test_les_attributs_d_evenement_disparaissent(self, enseignant):
        """« onerror » sur une image est le vecteur le plus courant."""
        article = Article.objects.create(
            titre="Piégé",
            auteur=enseignant,
            corps='<img src="x" onerror="alert(1)"><p onclick="voler()">Texte</p>',
        )
        article.refresh_from_db()
        assert "onerror" not in article.corps
        assert "onclick" not in article.corps

    def test_un_lien_javascript_est_neutralise(self, enseignant):
        """Le balisage est valide, et pourtant le clic exécuterait du code."""
        article = Article.objects.create(
            titre="Piégé", auteur=enseignant, corps='<a href="javascript:alert(1)">cliquez</a>'
        )
        article.refresh_from_db()
        assert "javascript:" not in article.corps

    def test_la_mise_en_forme_legitime_survit(self, enseignant):
        corps = (
            "<h2>Une section</h2><p><strong>gras</strong> et <em>italique</em></p>"
            "<ul><li>un</li><li>deux</li></ul><blockquote>Une citation</blockquote>"
            '<a href="https://exemple.org">un lien</a>'
        )
        article = Article.objects.create(titre="Propre", auteur=enseignant, corps=corps)
        article.refresh_from_db()
        for balise in ("<h2>", "<strong>", "<em>", "<ul>", "<li>", "<blockquote>"):
            assert balise in article.corps
        assert "https://exemple.org" in article.corps

    def test_les_liens_sortants_portent_noopener(self, enseignant):
        article = Article.objects.create(
            titre="Lien", auteur=enseignant, corps='<a href="https://exemple.org">ailleurs</a>'
        )
        article.refresh_from_db()
        assert "noopener" in article.corps

    def test_l_assainissement_vaut_pour_tout_chemin_d_ecriture(self, article):
        """Il vit dans « save », donc un import ou un shell y passent aussi."""
        article.corps = "<p>ok</p><script>alert(1)</script>"
        article.save()
        article.refresh_from_db()
        assert "<script" not in article.corps


# ══════════════════════════════════════════════
# Le cycle de publication
# ══════════════════════════════════════════════


class TestCycle:
    def test_un_article_naît_en_brouillon(self, article):
        assert article.statut == Article.Statut.BROUILLON
        assert not article.est_public

    def test_soumettre_sans_corps_est_refuse(self, enseignant):
        vide = Article.objects.create(titre="Sans corps", auteur=enseignant, corps="")
        with pytest.raises(ValidationError):
            vide.soumettre()

    def test_la_publication_exige_une_relecture(self, article):
        """Publier un brouillon sauterait le second regard — c'est tout l'objet."""
        with pytest.raises(ValidationError):
            article.publier()

    def test_le_parcours_nominal(self, article, relecteur):
        article.soumettre()
        assert article.statut == Article.Statut.RELECTURE

        article.publier(par=relecteur)
        assert article.est_public
        assert article.date_publication is not None
        assert article.relu_par == relecteur

    def test_un_renvoi_sans_motif_est_impossible(self, article):
        """Sans motif, l'auteur ne sait pas quoi corriger."""
        article.soumettre()
        with pytest.raises(ValidationError):
            article.renvoyer_en_brouillon("   ")
        assert article.statut == Article.Statut.RELECTURE

    def test_un_renvoi_motive_rouvre_la_redaction(self, article, relecteur):
        article.soumettre()
        article.renvoyer_en_brouillon("Les sources manquent.", par=relecteur)

        assert article.statut == Article.Statut.BROUILLON
        assert article.motif_refus == "Les sources manquent."
        assert article.est_modifiable

    def test_un_article_publie_n_est_pas_modifiable(self, article, relecteur):
        article.soumettre()
        article.publier(par=relecteur)
        assert not article.est_modifiable

    def test_le_retrait_rouvre_la_redaction(self, article, relecteur):
        article.soumettre()
        article.publier(par=relecteur)
        article.retirer(par=relecteur)

        assert article.statut == Article.Statut.RETIRE
        assert article.est_modifiable
        assert not article.est_public


# ══════════════════════════════════════════════
# Les écrans
# ══════════════════════════════════════════════


class TestEcransEnseignant:
    def test_l_enseignant_redige_un_article(self, client, enseignant):
        client.force_login(enseignant.user)
        reponse = client.post(
            reverse("website:article_creation"),
            {
                "titre": "Nouveau",
                "sous_titre": "",
                "chapeau": "",
                "corps": "<p>Texte</p>",
                "credit_image": "",
                "mots_cles": "",
            },
        )
        assert reponse.status_code == 302
        assert Article.objects.filter(titre="Nouveau", auteur=enseignant).exists()

    def test_on_ne_modifie_pas_l_article_d_un_collegue(self, client, db, article):
        autre = User.objects.create_user(
            username="autre_prof_art", email="apa@iteag.org", password=MOT_DE_PASSE, role=User.Role.ENSEIGNANT
        )
        Professeur.objects.create(nom="Autre", prenom="Prof", slug="autre-art", user=autre)

        client.force_login(autre)
        assert client.get(reverse("website:article_edition", args=[article.pk])).status_code == 404

    def test_la_soumission_avertit_les_relecteurs(self, client, enseignant, article, relecteur):
        client.force_login(enseignant.user)
        client.post(reverse("website:article_soumettre", args=[article.pk]))

        article.refresh_from_db()
        assert article.statut == Article.Statut.RELECTURE
        assert Notification.objects.filter(destinataire=relecteur).exists()

    def test_une_illustration_se_depose(self, client, enseignant, article):
        client.force_login(enseignant.user)
        image = SimpleUploadedFile("figure.png", _png_minimal(), content_type="image/png")

        client.post(
            reverse("website:article_illustration", args=[article.pk]),
            {"fichier": image, "legende": "Figure 1"},
        )
        assert article.illustrations.count() == 1

    def test_un_fichier_qui_n_est_pas_une_image_est_refuse(self, client, enseignant, article):
        """« ImageField » ouvre réellement le fichier : un .png menteur ne passe pas."""
        client.force_login(enseignant.user)
        faux = SimpleUploadedFile("piege.png", b"ceci n'est pas une image", content_type="image/png")

        client.post(
            reverse("website:article_illustration", args=[article.pk]),
            {"fichier": faux, "legende": ""},
        )
        assert article.illustrations.count() == 0

    def test_un_etudiant_n_accede_pas_a_la_redaction(self, client, db):
        etudiant = User.objects.create_user(
            username="etu_art", email="ea@iteag.org", password=MOT_DE_PASSE, role=User.Role.ETUDIANT
        )
        client.force_login(etudiant)
        assert client.get(reverse("website:mes_articles")).status_code in (302, 403)


class TestEcransRelecture:
    def test_le_relecteur_publie(self, client, article, relecteur):
        article.soumettre()
        client.force_login(relecteur)

        client.post(reverse("website:article_decision", args=[article.pk]), {"action": "publier"})

        article.refresh_from_db()
        assert article.est_public

    def test_l_auteur_est_averti_de_la_decision(self, client, article, relecteur, enseignant):
        article.soumettre()
        client.force_login(relecteur)
        client.post(reverse("website:article_decision", args=[article.pk]), {"action": "publier"})

        assert Notification.objects.filter(destinataire=enseignant.user).exists()

    def test_un_enseignant_ne_publie_pas_son_propre_article(self, client, article, enseignant):
        """Le second regard n'en serait plus un."""
        article.soumettre()
        client.force_login(enseignant.user)

        reponse = client.post(reverse("website:article_decision", args=[article.pk]), {"action": "publier"})

        assert reponse.status_code in (302, 403)
        article.refresh_from_db()
        assert not article.est_public


class TestPagesPubliques:
    def test_seuls_les_articles_publies_paraissent(self, client, article, relecteur):
        assert "ecclésiologie" not in client.get(reverse("website:articles")).content.decode()

        article.soumettre()
        article.publier(par=relecteur)
        assert "ecclésiologie" in client.get(reverse("website:articles")).content.decode()

    def test_un_brouillon_reste_illisible_meme_par_son_adresse(self, client, article):
        """Une adresse qui fuite ne doit pas ouvrir un texte non relu."""
        assert client.get(reverse("website:article_detail", args=[article.slug])).status_code == 404

    def test_l_article_publie_s_affiche_avec_sa_signature(self, client, article, relecteur):
        article.soumettre()
        article.publier(par=relecteur)

        contenu = client.get(reverse("website:article_detail", args=[article.slug])).content.decode()
        assert "Alain Nisus" in contenu
        assert "Un premier paragraphe" in contenu

    def test_la_recherche_filtre_les_articles(self, client, article, relecteur, enseignant):
        article.soumettre()
        article.publier(par=relecteur)
        autre = Article.objects.create(titre="Patristique latine", auteur=enseignant, corps="<p>x</p>")
        autre.soumettre()
        autre.publier(par=relecteur)

        contenu = client.get(reverse("website:articles"), {"q": "Patristique"}).content.decode()
        assert "Patristique latine" in contenu
        assert "ecclésiologie" not in contenu


class TestMarquageDeQuill:
    """Quill n'écrit pas le HTML qu'on croit, et le défaut est silencieux.

    Il encode **toutes** les listes en « <ol> », la puce étant portée par un
    attribut « data-list » que la liste blanche retire. Sans normalisation, une
    liste à puces ressortirait numérotée : le texte est là, seule la sémantique
    a changé, et cela ne se voit qu'à la lecture de l'article publié.

    Le balisage ci-dessous est celui relevé dans un navigateur, pas une
    reconstitution.
    """

    MARQUAGE_REEL = (
        "<h2>Titre</h2>"
        '<ol><li data-list="bullet"><span class="ql-ui" contenteditable="false"></span>puce un</li>'
        '<li data-list="bullet"><span class="ql-ui" contenteditable="false"></span>puce deux</li>'
        '<li data-list="ordered"><span class="ql-ui" contenteditable="false"></span>numero un</li></ol>'
    )

    def test_les_puces_redeviennent_une_liste_a_puces(self, enseignant):
        article = Article.objects.create(titre="Listes", auteur=enseignant, corps=self.MARQUAGE_REEL)
        article.refresh_from_db()
        assert "<ul><li>puce un</li><li>puce deux</li></ul>" in article.corps

    def test_les_numeros_restent_numerotes(self, enseignant):
        article = Article.objects.create(titre="Listes", auteur=enseignant, corps=self.MARQUAGE_REEL)
        article.refresh_from_db()
        assert "<ol><li>numero un</li></ol>" in article.corps

    def test_la_decoration_de_l_editeur_ne_survit_pas(self, enseignant):
        """« ql-ui » est un artefact d'édition : il n'a rien à faire dans l'article."""
        article = Article.objects.create(titre="Listes", auteur=enseignant, corps=self.MARQUAGE_REEL)
        article.refresh_from_db()
        assert "ql-ui" not in article.corps
        assert "data-list" not in article.corps

    def test_un_corps_sans_liste_traverse_intact(self, enseignant):
        article = Article.objects.create(titre="Sans liste", auteur=enseignant, corps="<h2>A</h2><p>Du texte.</p>")
        article.refresh_from_db()
        assert article.corps == "<h2>A</h2><p>Du texte.</p>"
