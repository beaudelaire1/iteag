"""
L'équipe professorale doit se voir depuis l'accueil.

Deux défauts se cumulaient dans la section « Équipe professorale » de la page
d'accueil :

1. le gabarit affichait des **initiales dans un rond**, jamais les photos, alors
   que le modèle porte un champ « photo » utilisé partout ailleurs ; il fallait
   ouvrir « Voir toute l'équipe » pour découvrir un visage ;
2. la fonction lisait « prof.titre_academique », un champ **qui n'existe pas**
   sur le modèle. La condition était donc toujours fausse : rien ne s'affichait
   sous les noms, et aucune erreur ne le signalait.
"""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from wagtail.models import Page

from apps.formations.models import Discipline, Professeur
from apps.website.models import HomePage

# Le plus petit PNG valide : la vignette n'a pas à être réaliste pour ce test.
PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
    b"\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00"
    b"\x00IEND\xaeB`\x82"
)


@pytest.fixture
def accueil(db):
    """Page d'accueil rattachée au site : sans cela, Wagtail ne sait pas la router."""
    from wagtail.models import Site

    racine = Page.objects.get(depth=1)
    page = HomePage(title="Accueil test équipe", slug="accueil-equipe", sous_titre="")
    racine.add_child(instance=page)
    site = Site.objects.get(is_default_site=True)
    site.root_page = page
    site.save(update_fields=["root_page"])
    return page


def photo(nom="prof.png"):
    return SimpleUploadedFile(nom, PNG, content_type="image/png")


@pytest.mark.django_db
class TestEquipeVisibleDesLAccueil:
    def test_la_photo_est_rendue(self, client, accueil):
        Professeur.objects.create(
            nom="Bélizaire",
            prenom="Samuel",
            slug="samuel-belizaire",
            specialite="Théologie systématique",
            photo=photo(),
        )
        contenu = client.get(accueil.url).content.decode()
        # Ancré sur « Notre équipe », propre à cette section : depuis le
        # regroupement de la barre publique, « Équipe professorale » y figure
        # aussi et serait rencontré en premier.
        section = contenu.split("Notre équipe", 1)[1].split("</section>", 1)[0]
        assert "<img" in section

    def test_la_fonction_est_affichee(self, client, accueil):
        """C'est ce que « titre_academique », champ inexistant, empêchait."""
        Professeur.objects.create(
            nom="Bélizaire",
            prenom="Samuel",
            slug="samuel-belizaire",
            specialite="Théologie systématique",
            photo=photo(),
        )
        assert "Théologie systématique" in client.get(accueil.url).content.decode()

    def test_a_defaut_de_specialite_les_disciplines_prennent_le_relais(self, client, accueil):
        professeur = Professeur.objects.create(nom="Nérée", prenom="Anne", slug="anne-neree", photo=photo())
        professeur.disciplines.add(Discipline.objects.create(nom="Éthique", slug="ethique-accueil"))
        assert "Éthique" in client.get(accueil.url).content.decode()

    def test_les_fiches_illustrees_passent_devant(self, client, accueil):
        """
        Sans cet ordre, la sélection pouvait n'afficher que des initiales alors
        que des photos existaient plus loin dans la liste.
        """
        for rang in range(4):
            Professeur.objects.create(nom=f"Sans{rang}", prenom="Photo", slug=f"sans-photo-{rang}", ordre=rang)
        Professeur.objects.create(
            nom="Avec", prenom="Photo", slug="avec-photo", ordre=99, specialite="Homilétique", photo=photo()
        )
        contexte = client.get(accueil.url).context
        assert contexte["featured_professeurs"][0].nom == "Avec"

    def test_la_page_complete_reste_accessible(self, client, accueil):
        """La sélection s'ajoute à la page d'équipe ; elle ne la remplace pas."""
        from django.urls import reverse

        Professeur.objects.create(nom="Bélizaire", prenom="Samuel", slug="samuel-belizaire", photo=photo())
        contenu = client.get(accueil.url).content.decode()
        assert reverse("formations:professeur_list") in contenu

    def test_un_professeur_inactif_n_apparait_pas(self, client, accueil):
        Professeur.objects.create(nom="Retiré", prenom="Jean", slug="jean-retire", actif=False, photo=photo())
        assert "Retiré" not in client.get(accueil.url).content.decode()

    def test_sans_photo_les_initiales_restent_le_repli(self, client, accueil):
        """Mieux vaut une initiale qu'un cadre vide : la fiche existe quand même."""
        Professeur.objects.create(nom="Duval", prenom="Marie", slug="marie-duval", specialite="Missiologie")
        contenu = client.get(accueil.url).content.decode()
        assert "Marie Duval" in contenu
        assert "Missiologie" in contenu
