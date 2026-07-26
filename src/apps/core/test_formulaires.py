"""
Aucun champ ne doit sortir non habillé.

Le défaut : chaque formulaire déclarait ses classes CSS lui-même, dans un
dictionnaire « widgets ». Ceux qui l'oubliaient rendaient des champs bruts —
dont le formulaire public de candidature, le plus visible du site : douze
champs sans bordure lisible sur le fond crème de la charte.

Le style est désormais posé en un seul endroit. Ce fichier vérifie qu'aucun
formulaire du projet n'échappe à cette règle, y compris ceux qui seront écrits
plus tard : c'est le recensement qui protège, pas une liste tenue à la main.
"""

import importlib
import inspect
import pkgutil

import pytest
from django import forms

from apps.core.formulaires import CLASSE_PAR_DEFAUT, INVISIBLES, classe_attendue


def formulaires_du_projet() -> list[type]:
    """Toutes les classes de formulaire déclarées dans « apps.*.forms »."""
    import apps

    trouves = []
    for module_info in pkgutil.iter_modules(apps.__path__):
        try:
            module = importlib.import_module(f"apps.{module_info.name}.forms")
        except ModuleNotFoundError:
            continue
        for _, objet in inspect.getmembers(module, inspect.isclass):
            if not issubclass(objet, forms.BaseForm) or objet.__module__ != module.__name__:
                continue
            trouves.append(objet)
    return sorted(trouves, key=lambda classe: f"{classe.__module__}.{classe.__name__}")


FORMULAIRES = formulaires_du_projet()


def test_le_recensement_trouve_bien_des_formulaires():
    """Sans cette vérification, une erreur d'import viderait la liste en silence."""
    assert len(FORMULAIRES) >= 20, f"Seulement {len(FORMULAIRES)} formulaires recensés"


@pytest.mark.django_db
@pytest.mark.parametrize("classe", FORMULAIRES, ids=lambda c: f"{c.__module__.split('.')[1]}.{c.__name__}")
def test_chaque_champ_porte_une_classe_du_systeme(classe):
    try:
        formulaire = classe()
    except TypeError:
        pytest.skip("Ce formulaire exige des arguments de construction.")

    nus = []
    for nom, champ in formulaire.fields.items():
        widget = champ.widget
        if isinstance(widget, INVISIBLES):
            continue
        if widget.attrs.get("aria-hidden") == "true":
            continue
        classes = widget.attrs.get("class", "").split()
        if not any(valeur.startswith("form-") for valeur in classes):
            nus.append(nom)
    assert not nus, f"Champs sans classe dans {classe.__name__} : {nus}"


def test_le_type_de_widget_decide_de_la_classe():
    """Une liste déroulante habillée en champ texte perd sa flèche et son fond."""
    assert classe_attendue(forms.Select()) == "form-select"
    assert classe_attendue(forms.CheckboxInput()) == "form-checkbox"
    assert classe_attendue(forms.ClearableFileInput()) == "form-file"
    assert classe_attendue(forms.TextInput()) == CLASSE_PAR_DEFAUT


@pytest.mark.django_db
def test_une_classe_deja_posee_est_conservee():
    """Le style complète les formulaires ; il ne défait pas leurs choix."""
    from apps.academics.forms import EnrollmentRequestForm

    formulaire = EnrollmentRequestForm()
    assert "form-file" in formulaire.fields["justificatif_paiement"].widget.attrs["class"]
    # Le gabarit posait déjà « form-input » sur ce champ : il n'est pas doublé.
    classes = formulaire.fields["note_etudiant"].widget.attrs["class"].split()
    assert classes.count("form-input") == 1


@pytest.mark.django_db
def test_le_piege_a_robots_reste_invisible():
    """Habiller un champ caché lui donnerait une bordure : il cesserait d'être un piège."""
    from apps.core.forms import NewsletterForm

    formulaire = NewsletterForm()
    assert "form-" not in formulaire.fields["site_web"].widget.attrs.get("class", "")


@pytest.mark.django_db
class TestLeChampRefuseSeVoit:
    """Un message sous le champ ne suffit pas : l'œil ne le relie pas toujours au bon endroit."""

    def test_le_conteneur_porte_l_etat(self, client):
        from django.urls import reverse

        reponse = client.post(reverse("admissions:candidature_form"), {"nom": ""})
        assert reponse.status_code == 200
        assert "champ--invalide" in reponse.content.decode()

    def test_un_formulaire_valide_n_affiche_aucune_erreur(self, client):
        from django.urls import reverse

        contenu = client.get(reverse("admissions:candidature_form")).content.decode()
        assert "champ--invalide" not in contenu
        assert "form-erreur" not in contenu
