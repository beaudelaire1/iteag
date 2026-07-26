"""
Ce que la barre latérale de chaque espace doit garantir.

Trois défauts vivaient ici, qu'aucun test ne voyait :

1. **des ancres imbriquées** — trois liens avaient été insérés à l'intérieur
   du lien « Paiements », entre sa balise ouvrante et son libellé. Le HTML est
   invalide ; les navigateurs referment l'ancre d'autorité, et ce qui suit
   cesse d'être cliquable comme prévu ;
2. **une page de portail sans navigation du tout** — l'accueil enseignant
   s'affichait avec une colonne latérale vide ;
3. **deux chartes graphiques** — la moitié des liens en `blue-700`/`gray-700`,
   l'autre aux couleurs ITEAG.

Le rendu est examiné, pas la source : c'est ce que l'utilisateur reçoit.
"""

from html.parser import HTMLParser

import pytest
from django.urls import reverse

from apps.academics.models import ProfilEtudiant, Promotion
from apps.accounts.models import User
from apps.formations.models import Parcours, Professeur


class _AncresImbriquees(HTMLParser):
    """Relève toute ancre ouverte alors qu'une autre l'est déjà."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.profondeur = 0
        self.fautes: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag != "a":
            return
        if self.profondeur:
            self.fautes.append(dict(attrs).get("href", "(sans href)"))
        self.profondeur += 1

    def handle_endtag(self, tag):
        if tag == "a" and self.profondeur:
            self.profondeur -= 1


def ancres_imbriquees(html: str) -> list[str]:
    analyseur = _AncresImbriquees()
    analyseur.feed(html)
    return analyseur.fautes


@pytest.fixture
def parcours(db):
    return Parcours.objects.create(
        nom="Diplômant", slug="diplomant-nav", type_parcours=Parcours.TypeParcours.DIPLOMANT_ITEAG
    )


@pytest.fixture
def comptes(db, parcours):
    faits = {}
    for role in (User.Role.ADMIN, User.Role.SECRETARIAT, User.Role.ENSEIGNANT, User.Role.ETUDIANT):
        faits[role] = User.objects.create_user(
            username=f"nav_{role}",
            email=f"nav_{role}@iteag.org",
            password="motdepasse-long-12",
            first_name="Test",
            last_name=role.capitalize(),
            role=role,
        )
    Professeur.objects.create(user=faits[User.Role.ENSEIGNANT], nom="Nav", prenom="Prof", slug="prof-nav")
    promotion = Promotion.objects.create(nom="Promo nav", parcours=parcours, annee_debut=2026, annee_fin=2032)
    ProfilEtudiant.objects.create(
        utilisateur=faits[User.Role.ETUDIANT],
        parcours=parcours,
        promotion=promotion,
        numero_etudiant="ETU-NAV-1",
        statut_inscription=ProfilEtudiant.StatutInscription.ACTIF,
    )
    return faits


# Un écran par espace : celui sur lequel chaque rôle atterrit en se connectant.
ACCUEILS = {
    User.Role.ETUDIANT: "etudiant:dashboard",
    User.Role.ENSEIGNANT: "enseignant:accueil",
    User.Role.SECRETARIAT: "secretariat:dashboard",
    User.Role.ADMIN: "administration:dashboard",
}


@pytest.mark.django_db
@pytest.mark.parametrize("role,nom_route", sorted(ACCUEILS.items()))
class TestBarreDeNavigation:
    def _rendu(self, client, comptes, role, nom_route) -> str:
        client.force_login(comptes[role])
        reponse = client.get(reverse(nom_route))
        assert reponse.status_code == 200, f"{nom_route} → {reponse.status_code}"
        return reponse.content.decode()

    def test_aucune_ancre_imbriquee(self, client, comptes, role, nom_route):
        fautes = ancres_imbriquees(self._rendu(client, comptes, role, nom_route))
        assert not fautes, f"Ancres imbriquées dans « {nom_route} » : {fautes}"

    def test_la_navigation_est_presente(self, client, comptes, role, nom_route):
        """Une colonne latérale vide laisse croire à une panne."""
        contenu = self._rendu(client, comptes, role, nom_route)
        assert "portal-nav-link" in contenu, f"Aucune navigation de portail sur « {nom_route} »"

    def test_une_seule_charte(self, client, comptes, role, nom_route):
        """
        Les couleurs par défaut de Tailwind ne sont pas celles de l'ITEAG : leur
        présence signale un écran resté hors du système de composants.
        """
        contenu = self._rendu(client, comptes, role, nom_route)
        etrangeres = [classe for classe in ("bg-blue-50", "bg-blue-700", "text-blue-700") if classe in contenu]
        assert not etrangeres, f"Couleurs hors charte sur « {nom_route} » : {etrangeres}"

    def test_aucun_lien_en_double(self, client, comptes, role, nom_route):
        """Un même écran atteignable deux fois depuis la même barre désoriente."""
        import re

        contenu = self._rendu(client, comptes, role, nom_route)
        barre = contenu.split('<nav class="sticky', 1)[-1].split("</nav>", 1)[0]
        liens = re.findall(r'href="([^"#]+)"', barre)
        doublons = {lien for lien in liens if liens.count(lien) > 1}
        assert not doublons, f"Liens répétés dans la barre de « {nom_route} » : {doublons}"


# Couleurs de la palette Tailwind par défaut. Elles ne font pas partie de la
# charte ITEAG : navy, gold et warm sont les seules familles définies dans le
# thème. En trouver une signale un écran qui n'a pas été rattaché au système de
# composants — c'est ainsi que le projet s'est retrouvé avec deux apparences.
FAMILLES_ETRANGERES = ("gray", "blue", "yellow", "purple", "slate", "zinc", "stone", "neutral")

# Les gabarits d'impression PDF ne partagent pas la feuille de style du site :
# ils déclarent leurs couleurs en clair, et n'ont pas de classes utilitaires.
GABARITS_HORS_CHARTE = {"documents/pdf/document.html", "elearning/attestation_pdf.html", "core/emails/base_email.html"}


def test_une_seule_charte_dans_tous_les_gabarits():
    """
    Vérifié sur la source, et pas seulement sur quatre écrans rendus : le
    contrôle par le rendu ne voit que les pages qu'on a pensé à visiter.
    """
    import re
    from pathlib import Path

    racine = Path(__file__).resolve().parents[2] / "templates"
    motif = re.compile(r"\b(?:bg|text|border|divide|ring)-(" + "|".join(FAMILLES_ETRANGERES) + r")-\d{2,3}\b")

    fautifs = []
    for gabarit in sorted(racine.rglob("*.html")):
        relatif = gabarit.relative_to(racine).as_posix()
        if relatif in GABARITS_HORS_CHARTE:
            continue
        for numero, ligne in enumerate(gabarit.read_text(encoding="utf-8").splitlines(), 1):
            trouve = motif.findall(ligne)
            if trouve:
                fautifs.append(f"  {relatif}:{numero} → {sorted(set(trouve))}")

    assert not fautifs, "Couleurs hors charte ITEAG :\n" + "\n".join(fautifs)
