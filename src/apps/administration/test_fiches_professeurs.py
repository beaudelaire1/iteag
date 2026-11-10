"""Les rubriques de la fiche publique se corrigent depuis le portail."""

import pytest
from bs4 import BeautifulSoup
from django.urls import reverse

from apps.accounts.models import User
from apps.formations.models import Discipline, Professeur

pytestmark = pytest.mark.django_db


@pytest.fixture(params=[User.Role.ADMIN, User.Role.SECRETARIAT])
def gestionnaire(request):
    return User.objects.create_user(username="gestion_fiches", email="fiches@example.org", role=request.param)


@pytest.fixture
def professeur():
    return Professeur.objects.create(
        prenom="Alain",
        nom="Nisus",
        slug="alain-nisus-fiche",
        biographie="Présentation initiale",
        specialite="Théologie",
        parcours_academique=[
            {"annee": "Depuis 2022", "description": "Professeur associé"},
            {"annee": "2008", "description": "Doctorat en théologie"},
        ],
        expertises=["Ecclésiologie", "Éthique"],
        autres_engagements="Aumônerie",
        publications_ouvrages="Ouvrage initial",
        publications_articles="Article initial",
        cours_enseignes=["Christologie", "Herméneutique"],
    )


def donnees_fiche(professeur=None, etapes=()):
    donnees = {
        "prenom": professeur.prenom if professeur else "Élie",
        "nom": professeur.nom if professeur else "Bernard",
        "slug": professeur.slug if professeur else "",
        "biographie": "Présentation corrigée",
        "specialite": "Théologie systématique",
        "expertises": " Ecclésiologie \r\n\r\n Éthique ",
        "autres_engagements": "Conseil scientifique\nAumônerie",
        "publications_ouvrages": "Premier ouvrage\nDeuxième ouvrage",
        "publications_articles": "Article corrigé",
        "cours_enseignes": " Christologie \n\n Herméneutique ",
        "actif": "on",
        "ordre": "0",
        "parcours-TOTAL_FORMS": str(len(etapes)),
        "parcours-INITIAL_FORMS": str(len(professeur.parcours_academique) if professeur else 0),
    }
    for index, etape in enumerate(etapes):
        donnees.update({f"parcours-{index}-{nom}": valeur for nom, valeur in etape.items()})
    return donnees


def test_le_formulaire_restitue_toutes_les_rubriques_existantes(client, gestionnaire, professeur):
    client.force_login(gestionnaire)
    reponse = client.get(reverse("administration:professeur_update", args=[professeur.pk]))
    assert reponse.status_code == 200
    page = BeautifulSoup(reponse.content, "html.parser")
    assert page.find("input", {"name": "parcours-0-annee"})["value"] == "Depuis 2022"
    assert page.find("textarea", {"name": "parcours-1-description"}).text.strip() == "Doctorat en théologie"
    for nom, attendu in {
        "expertises": "Ecclésiologie\nÉthique",
        "autres_engagements": "Aumônerie",
        "publications_ouvrages": "Ouvrage initial",
        "publications_articles": "Article initial",
        "cours_enseignes": "Christologie\nHerméneutique",
    }.items():
        assert page.find("textarea", {"name": nom}).text.strip() == attendu
    assert page.select_one("template[data-parcours-modele] input[name='parcours-__prefix__-annee']")


def test_modifier_ajouter_retirer_et_reordonner_est_visible_sur_le_site(client, gestionnaire, professeur):
    client.force_login(gestionnaire)
    discipline = Discipline.objects.create(nom="Théologie systématique", slug="theologie-fiche")
    donnees = donnees_fiche(
        professeur,
        etapes=[
            {"annee": "Depuis 2023", "description": "Professeur titulaire", "ORDER": "2"},
            {"annee": "2008", "description": "Doctorat en théologie", "DELETE": "on"},
            {"annee": "2026", "description": "Direction de recherche", "ORDER": "1"},
            {},  # La ligne supplémentaire vide ne devient pas une étape.
        ],
    )
    donnees["disciplines"] = [discipline.pk]
    reponse = client.post(reverse("administration:professeur_update", args=[professeur.pk]), donnees)
    assert reponse.status_code == 302
    professeur.refresh_from_db()
    assert professeur.parcours_academique == [
        {"annee": "2026", "description": "Direction de recherche"},
        {"annee": "Depuis 2023", "description": "Professeur titulaire"},
    ]
    assert professeur.expertises == ["Ecclésiologie", "Éthique"]
    assert professeur.cours_enseignes == ["Christologie", "Herméneutique"]
    assert list(professeur.disciplines.all()) == [discipline]
    client.logout()
    publique = client.get(professeur.get_absolute_url())
    assert publique.status_code == 200
    texte = BeautifulSoup(publique.content, "html.parser").get_text()
    for contenu in (
        "Présentation corrigée",
        "Théologie systématique",
        "Depuis 2023",
        "Ecclésiologie",
        "Éthique",
        "Conseil scientifique",
        "Premier ouvrage",
        "Deuxième ouvrage",
        "Article corrigé",
        "Christologie",
        "Herméneutique",
    ):
        assert contenu in texte
    assert texte.index("Direction de recherche") < texte.index("Professeur titulaire")
    assert "Doctorat en théologie" not in texte


def test_creer_une_fiche_complete_sans_javascript(client, gestionnaire):
    client.force_login(gestionnaire)
    donnees = donnees_fiche(etapes=[{"annee": "2006 – 2018", "description": "Enseignant"}])
    reponse = client.post(reverse("administration:professeur_create"), donnees)
    assert reponse.status_code == 302
    professeur = Professeur.objects.get(slug="elie-bernard")
    assert professeur.parcours_academique == [{"annee": "2006 – 2018", "description": "Enseignant"}]
    assert professeur.expertises == ["Ecclésiologie", "Éthique"]
    assert professeur.cours_enseignes == ["Christologie", "Herméneutique"]
    assert professeur.publications_articles == "Article corrigé"


def test_les_rubriques_peuvent_etre_videes(client, gestionnaire, professeur):
    client.force_login(gestionnaire)
    donnees = donnees_fiche(professeur, etapes=[{"DELETE": "on"}, {"DELETE": "on"}, {}])
    for nom in (
        "expertises",
        "cours_enseignes",
        "autres_engagements",
        "publications_ouvrages",
        "publications_articles",
    ):
        donnees[nom] = ""
    reponse = client.post(reverse("administration:professeur_update", args=[professeur.pk]), donnees)
    assert reponse.status_code == 302
    professeur.refresh_from_db()
    assert professeur.parcours_academique == []
    assert professeur.expertises == []
    assert professeur.cours_enseignes == []
    assert professeur.autres_engagements == ""
    assert professeur.publications_ouvrages == ""
    assert professeur.publications_articles == ""
    publique = client.get(professeur.get_absolute_url())
    texte = BeautifulSoup(publique.content, "html.parser").get_text()
    assert "Parcours académique" not in texte
    assert "Expertises académiques" not in texte
    assert "Publications" not in texte


def test_une_etape_incomplete_bloque_toute_modification_et_conserve_la_saisie(client, gestionnaire, professeur):
    client.force_login(gestionnaire)
    donnees = donnees_fiche(
        professeur,
        etapes=[
            {"annee": "Depuis 2024", "description": "Correction en attente"},
            {"annee": "2008", "description": "Doctorat en théologie"},
            {"annee": "2026", "description": ""},
        ],
    )
    reponse = client.post(reverse("administration:professeur_update", args=[professeur.pk]), donnees)
    assert reponse.status_code == 200
    form = reponse.context["form"]
    assert "description" in form.parcours.forms[2].errors
    page = BeautifulSoup(reponse.content, "html.parser")
    assert page.find("textarea", {"name": "parcours-0-description"}).text.strip() == "Correction en attente"
    assert page.find("input", {"name": "parcours-2-annee"})["value"] == "2026"
    professeur.refresh_from_db()
    assert professeur.biographie == "Présentation initiale"
    assert professeur.parcours_academique[0]["annee"] == "Depuis 2022"
    assert professeur.publications_ouvrages == "Ouvrage initial"


def test_une_erreur_sur_la_fiche_conserve_les_nouvelles_etapes(client, gestionnaire):
    client.force_login(gestionnaire)
    donnees = donnees_fiche(etapes=[{"annee": "Depuis 2026", "description": "Nouvelle activité"}])
    donnees["nom"] = ""
    reponse = client.post(reverse("administration:professeur_create"), donnees)
    assert reponse.status_code == 200
    assert "nom" in reponse.context["form"].errors
    assert "Nouvelle activité" in reponse.content.decode()
    assert not Professeur.objects.exists()


def test_un_envoi_sans_parcours_nefface_pas_les_donnees(client, gestionnaire, professeur):
    client.force_login(gestionnaire)
    donnees = {nom: valeur for nom, valeur in donnees_fiche(professeur).items() if not nom.startswith("parcours-")}
    reponse = client.post(reverse("administration:professeur_update", args=[professeur.pk]), donnees)
    assert reponse.status_code == 200
    assert reponse.context["form"].parcours.non_form_errors()
    professeur.refresh_from_db()
    assert professeur.biographie == "Présentation initiale"
    assert len(professeur.parcours_academique) == 2


@pytest.mark.parametrize("role", [User.Role.ETUDIANT, User.Role.ENSEIGNANT])
def test_les_fiches_restent_reservees_aux_gestionnaires(client, professeur, role):
    compte = User.objects.create_user(username="sans_gestion", email="sans-gestion@example.org", role=role)
    client.force_login(compte)
    url = reverse("administration:professeur_update", args=[professeur.pk])
    assert client.get(url).status_code == 403
    assert client.post(url, donnees_fiche(professeur)).status_code == 403
    professeur.refresh_from_db()
    assert professeur.biographie == "Présentation initiale"
