"""
Tests des ressources pédagogiques de leçon.

Deux enjeux, dans l'ordre d'importance :

* le **droit** : un support de leçon obéit à la même politique d'accès que la
  leçon elle-même. Un module protégé dont les PDF seraient en accès libre
  n'aurait de protégé que la vidéo.
* le **cloisonnement enseignant** : un enseignant ne dépose et ne retire des
  ressources que sur ses propres leçons.
"""

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.accounts.models import User
from apps.elearning.models import ModuleFormation, RessourceLecon
from apps.formations.models import Professeur


def _pdf(nom="notes-de-cours.pdf"):
    return SimpleUploadedFile(nom, b"%PDF-1.4 contenu factice", content_type="application/pdf")


@pytest.fixture
def ressource(db, lecon, enseignant):
    return RessourceLecon.objects.create(
        lecon=lecon,
        titre="Notes de cours",
        fichier=_pdf(),
        deposee_par=enseignant.user,
        ordre=1,
    )


@pytest.fixture
def autre_enseignant(db):
    utilisateur = User.objects.create_user(
        username="autreprof",
        email="autreprof@iteag.org",
        password="motdepasse-long-12",
        role=User.Role.ENSEIGNANT,
    )
    return Professeur.objects.create(user=utilisateur, nom="Labeth", prenom="Ruth", slug="ruth-labeth")


def _url_depot(lecon):
    return reverse("elearning:enseignant_ressource_creer", kwargs={"lecon_pk": lecon.pk})


def _url_telechargement(ressource):
    lecon = ressource.lecon
    return reverse(
        "elearning:ressource_telecharger",
        kwargs={"slug": lecon.chapitre.module.slug, "lecon_slug": lecon.slug, "pk": ressource.pk},
    )


@pytest.mark.django_db
class TestModele:
    def test_une_ressource_porte_un_fichier_ou_un_lien_jamais_les_deux(self, lecon):
        ressource = RessourceLecon(lecon=lecon, titre="Ambiguë", fichier=_pdf(), lien_externe="https://exemple.org/")
        with pytest.raises(ValidationError):
            ressource.full_clean()

    def test_une_ressource_sans_rien_est_refusee(self, lecon):
        with pytest.raises(ValidationError):
            RessourceLecon(lecon=lecon, titre="Vide").full_clean()

    def test_la_taille_et_le_nom_d_origine_sont_figes_au_depot(self, ressource):
        assert ressource.taille_octets > 0
        assert ressource.nom_origine == "notes-de-cours.pdf"
        assert ressource.nom_fichier == "notes-de-cours.pdf"
        assert ressource.extension == "pdf"


@pytest.mark.django_db
class TestDepotParLEnseignant:
    def test_depot_d_un_fichier(self, client, enseignant, lecon):
        client.force_login(enseignant.user)
        reponse = client.post(_url_depot(lecon), {"titre": "Plan du cours", "fichier": _pdf("plan.pdf")})
        assert reponse.status_code == 302
        ressource = RessourceLecon.objects.get(lecon=lecon, titre="Plan du cours")
        assert ressource.deposee_par == enseignant.user
        assert ressource.ordre == 1

    def test_depot_d_un_lien(self, client, enseignant, lecon):
        client.force_login(enseignant.user)
        client.post(_url_depot(lecon), {"titre": "Article", "lien_externe": "https://exemple.org/article"})
        assert RessourceLecon.objects.filter(lecon=lecon, lien_externe="https://exemple.org/article").exists()

    def test_l_ordre_s_incremente_automatiquement(self, client, enseignant, lecon, ressource):
        client.force_login(enseignant.user)
        client.post(_url_depot(lecon), {"titre": "Annexe", "fichier": _pdf("annexe.pdf")})
        assert RessourceLecon.objects.get(lecon=lecon, titre="Annexe").ordre == 2

    def test_un_format_hors_liste_est_refuse(self, client, enseignant, lecon):
        client.force_login(enseignant.user)
        executable = SimpleUploadedFile("outil.exe", b"MZ...", content_type="application/octet-stream")
        client.post(_url_depot(lecon), {"titre": "Outil", "fichier": executable})
        assert not RessourceLecon.objects.filter(lecon=lecon).exists()

    def test_un_lien_non_https_est_refuse(self, client, enseignant, lecon):
        client.force_login(enseignant.user)
        client.post(_url_depot(lecon), {"titre": "Article", "lien_externe": "http://exemple.org/"})
        assert not RessourceLecon.objects.filter(lecon=lecon).exists()

    def test_je_ne_depose_pas_sur_la_lecon_d_un_autre(self, client, autre_enseignant, lecon):
        client.force_login(autre_enseignant.user)
        reponse = client.post(_url_depot(lecon), {"titre": "Intrusion", "fichier": _pdf()})
        assert reponse.status_code == 404
        assert not RessourceLecon.objects.filter(lecon=lecon).exists()

    def test_je_ne_retire_pas_la_ressource_d_un_autre(self, client, autre_enseignant, ressource):
        client.force_login(autre_enseignant.user)
        reponse = client.post(reverse("elearning:enseignant_ressource_supprimer", kwargs={"pk": ressource.pk}))
        assert reponse.status_code == 404
        assert RessourceLecon.objects.filter(pk=ressource.pk).exists()

    def test_le_retrait_supprime_la_ressource(self, client, enseignant, ressource):
        client.force_login(enseignant.user)
        reponse = client.post(reverse("elearning:enseignant_ressource_supprimer", kwargs={"pk": ressource.pk}))
        assert reponse.status_code == 302
        assert not RessourceLecon.objects.filter(pk=ressource.pk).exists()

    def test_la_page_d_edition_montre_les_ressources(self, client, enseignant, ressource):
        client.force_login(enseignant.user)
        contenu = client.get(
            reverse("elearning:enseignant_lecon_modifier", kwargs={"pk": ressource.lecon.pk})
        ).content.decode()
        assert "Ressources pédagogiques" in contenu
        assert ressource.titre in contenu


@pytest.mark.django_db
class TestTelechargementParLEtudiant:
    def test_sans_droit_le_telechargement_est_refuse(self, client, ressource):
        """Module réservé aux inscrits : un anonyme est renvoyé vers la leçon."""
        reponse = client.get(_url_telechargement(ressource))
        assert reponse.status_code == 302
        assert reponse.url == reverse(
            "elearning:lecon_detail",
            kwargs={"slug": ressource.lecon.chapitre.module.slug, "lecon_slug": ressource.lecon.slug},
        )

    def test_avec_droit_le_fichier_est_remis(self, client, ressource, profil, acces, utilisateur_etudiant):
        client.force_login(utilisateur_etudiant)
        reponse = client.get(_url_telechargement(ressource))
        assert reponse.status_code == 200
        assert reponse["Content-Disposition"].startswith("attachment")
        assert "notes-de-cours.pdf" in reponse["Content-Disposition"]

    def test_une_ressource_lien_redirige_vers_le_lien(self, client, lecon, profil, acces, utilisateur_etudiant):
        ressource = RessourceLecon.objects.create(
            lecon=lecon, titre="Article", lien_externe="https://exemple.org/article"
        )
        client.force_login(utilisateur_etudiant)
        reponse = client.get(_url_telechargement(ressource))
        assert reponse.status_code == 302
        assert reponse.url == "https://exemple.org/article"

    def test_module_public_le_telechargement_est_libre(self, client, ressource):
        module = ressource.lecon.chapitre.module
        module.politique_acces = ModuleFormation.PolitiqueAcces.PUBLIC
        module.save(update_fields=["politique_acces"])
        reponse = client.get(_url_telechargement(ressource))
        assert reponse.status_code == 200

    def test_la_page_de_lecon_liste_les_ressources(self, client, ressource, profil, acces, utilisateur_etudiant):
        client.force_login(utilisateur_etudiant)
        lecon = ressource.lecon
        contenu = client.get(
            reverse(
                "elearning:lecon_detail",
                kwargs={"slug": lecon.chapitre.module.slug, "lecon_slug": lecon.slug},
            )
        ).content.decode()
        assert "Ressources de la leçon" in contenu
        assert ressource.titre in contenu
