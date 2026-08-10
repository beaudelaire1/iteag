"""
Une liste paginée doit être parcourable.

Douze écrans déclaraient « paginate_by » sans jamais afficher la moindre
commande de pagination : au-delà de la première page, les données existaient
mais restaient hors d'atteinte. Le défaut ne se voit qu'avec assez de lignes
pour dépasser la page — c'est-à-dire jamais pendant le développement, et
toujours en exploitation.

Le second défaut se voit encore moins : les liens s'écrivaient « ?page=2 »
tout court. Passer à la page suivante d'une liste filtrée effaçait la
recherche et rendait un autre jeu de résultats, sans le signaler.
"""

import pathlib
import re

import pytest
from django.urls import reverse

from apps.academics.models import ProfilEtudiant, Promotion
from apps.accounts.models import User
from apps.formations.models import Parcours

RACINE = pathlib.Path(__file__).resolve().parents[2]
TEMPLATES = RACINE / "templates"
INCLUSION_STATIQUE = re.compile(r'{%\s*include\s+["\']([^"\']+)["\']')


def vues_paginees() -> list[tuple[str, str]]:
    """(module, classe) de toutes les vues du projet qui déclarent « paginate_by »."""
    trouvees = []
    for fichier in sorted((RACINE / "apps").rglob("*.py")):
        if fichier.name.startswith("test") or "migrations" in fichier.parts:
            continue
        texte = fichier.read_text(encoding="utf-8")
        if "paginate_by" not in texte:
            continue
        for bloc in re.split(r"\n(?=class )", texte):
            if "paginate_by" in bloc and bloc.startswith("class "):
                nom_classe = bloc.split("(")[0].replace("class ", "").strip()
                gabarit = re.search(r'template_name\s*=\s*["\']([^"\']+)["\']', bloc)
                if gabarit:
                    trouvees.append((nom_classe, gabarit.group(1)))
    return sorted(set(trouvees))


def gabarit_offre_pagination(chemin: pathlib.Path, visites: set[pathlib.Path] | None = None) -> bool:
    """Suit les inclusions statiques : la pagination peut vivre dans un partial HTMX."""
    visites = visites or set()
    chemin = chemin.resolve()
    if chemin in visites or not chemin.exists():
        return False
    visites.add(chemin)

    texte = chemin.read_text(encoding="utf-8")
    if "partials/pagination.html" in texte or "page_obj.has_other_pages" in texte:
        return True

    for nom in INCLUSION_STATIQUE.findall(texte):
        inclus = TEMPLATES / nom
        if gabarit_offre_pagination(inclus, visites):
            return True
    return False


VUES = vues_paginees()


def test_le_recensement_trouve_bien_des_vues():
    """Une erreur de lecture viderait la liste, et le test passerait sans rien vérifier."""
    assert len(VUES) >= 15, f"Seulement {len(VUES)} vues paginées recensées"


@pytest.mark.parametrize("classe,gabarit", VUES, ids=lambda valeur: valeur if isinstance(valeur, str) else "")
def test_chaque_liste_paginee_offre_ses_commandes(classe, gabarit):
    chemin = TEMPLATES / gabarit
    if not chemin.exists():
        pytest.skip(f"Gabarit introuvable : {gabarit}")
    assert gabarit_offre_pagination(chemin), f"{classe} pagine mais « {gabarit} » n'affiche aucune commande"


@pytest.mark.django_db
class TestLesFiltresSurviventAuChangementDePage:
    @pytest.fixture
    def administrateur(self, db):
        return User.objects.create_user(
            username="admin_pag", email="apg@iteag.org", password="motdepasse-long-12", role=User.Role.ADMIN
        )

    @pytest.fixture
    def beaucoup_d_etudiants(self, db):
        parcours = Parcours.objects.create(
            nom="Diplômant", slug="diplomant-pag", type_parcours=Parcours.TypeParcours.DIPLOMANT_ITEAG
        )
        promotion = Promotion.objects.create(nom="Promo pag", parcours=parcours, annee_debut=2027, annee_fin=2033)
        for rang in range(25):
            utilisateur = User.objects.create_user(
                username=f"etu_pag_{rang}",
                email=f"ep{rang}@iteag.org",
                password="motdepasse-long-12",
                first_name="Martin",
                last_name=f"Nom{rang}",
                role=User.Role.ETUDIANT,
            )
            ProfilEtudiant.objects.create(
                utilisateur=utilisateur,
                parcours=parcours,
                promotion=promotion,
                numero_etudiant=f"ETU-PAG-{rang}",
                statut_inscription=ProfilEtudiant.StatutInscription.ACTIF,
            )
        return parcours

    def test_la_seconde_page_est_atteignable(self, client, administrateur, beaucoup_d_etudiants):
        client.force_login(administrateur)
        contenu = client.get(reverse("administration:etudiants")).content.decode()
        assert "page=2" in contenu, "Aucun lien vers la seconde page"

    def test_le_lien_conserve_la_recherche(self, client, administrateur, beaucoup_d_etudiants):
        """Sans cela, changer de page effacerait le filtre sans le dire."""
        client.force_login(administrateur)
        contenu = client.get(reverse("administration:etudiants"), {"q": "Martin"}).content.decode()
        lien = re.search(r'href="(\?[^"]*page=2[^"]*)"', contenu)
        assert lien, "Aucun lien vers la seconde page"
        assert "q=Martin" in lien.group(1), f"La recherche est perdue : {lien.group(1)}"

    def test_le_nombre_total_de_resultats_est_annonce(self, client, administrateur, beaucoup_d_etudiants):
        client.force_login(administrateur)
        assert "25 résultats" in client.get(reverse("administration:etudiants")).content.decode()
