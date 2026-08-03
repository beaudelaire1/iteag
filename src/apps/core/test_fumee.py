"""
Test de fumée : toutes les routes sans argument, pour chaque rôle.

Ce que ce fichier attrape et qu'aucun autre test ne voit : une variable de
contexte oubliée, un `{% url %}` vers une route renommée, un gabarit qui
référence un champ disparu. Ces fautes ne cassent ni le lint ni les tests
unitaires — elles produisent une erreur 500 devant l'utilisateur.

Deux propriétés sont vérifiées pour chaque route et chaque rôle :

1. **aucune erreur serveur** — une 500 est toujours un défaut, quel que soit le
   visiteur ;
2. **le cloisonnement** — une page d'administration ne doit jamais répondre 200
   à un étudiant. Un test de fumée qui ne regarderait que « ça ne plante pas »
   laisserait passer une fuite de droits.
"""

import pytest
from django.urls import reverse

from apps.academics.models import ProfilEtudiant, Promotion
from apps.accounts.models import User
from apps.formations.models import Parcours, Professeur

# Routes exclues et pourquoi. Toute exclusion doit se justifier : sans cela, le
# fichier se viderait au premier test gênant.
EXCLUES = {
    "accounts:logout",  # déconnecte, ce qui fausse les vérifications suivantes
    "administration:acces_action",  # POST seul, agit sur des données
    "core:notifications_tout_lire",  # idem
}

# Routes qui répondent en flux binaire ou en pièce jointe.
EXPORTS = {
    "administration:export_candidatures",
    "administration:export_etudiants",
    "administration:export_paiements",
    "administration:acces_export",
}


def routes_sans_argument() -> list[str]:
    """Noms de toutes les routes du projet qui n'attendent aucun paramètre."""
    from django.urls import get_resolver

    internes = ("wagtail", "admin:", "django")
    noms = []

    def parcourir(resolver, prefixe=""):
        for motif in resolver.url_patterns:
            if hasattr(motif, "url_patterns"):
                parcourir(motif, prefixe + (motif.namespace + ":" if motif.namespace else ""))
            elif motif.name and motif.pattern.regex.groups == 0:
                nom = prefixe + motif.name
                if not nom.startswith(internes) and nom not in EXCLUES:
                    noms.append(nom)

    parcourir(get_resolver())
    return sorted(set(noms))


ROUTES = routes_sans_argument()

# Préfixes réservés au personnel. Un étudiant ou un enseignant qui obtient 200
# sur l'un d'eux est une fuite de droits, pas une commodité.
PREFIXES_PERSONNEL = ("administration:", "secretariat:")


@pytest.fixture
def parcours(db):
    return Parcours.objects.create(
        nom="Diplômant", slug="diplomant-fumee", type_parcours=Parcours.TypeParcours.DIPLOMANT_ITEAG
    )


@pytest.fixture
def comptes(db, parcours):
    """Un compte par rôle, chacun doté du profil que son portail exige."""
    faits = {}

    for role in (User.Role.ADMIN, User.Role.SECRETARIAT, User.Role.ENSEIGNANT, User.Role.ETUDIANT):
        faits[role] = User.objects.create_user(
            username=f"fumee_{role}",
            email=f"fumee_{role}@iteag.org",
            password="motdepasse-long-12",
            first_name="Test",
            last_name=role.capitalize(),
            role=role,
        )

    Professeur.objects.create(user=faits[User.Role.ENSEIGNANT], nom="Fumée", prenom="Prof", slug="prof-fumee")
    promotion = Promotion.objects.create(nom="Promo fumée", parcours=parcours, annee_debut=2026, annee_fin=2032)
    ProfilEtudiant.objects.create(
        utilisateur=faits[User.Role.ETUDIANT],
        parcours=parcours,
        promotion=promotion,
        numero_etudiant="ETU-FUMEE-1",
        statut_inscription=ProfilEtudiant.StatutInscription.ACTIF,
    )
    return faits


@pytest.mark.django_db
@pytest.mark.parametrize("nom_route", ROUTES)
class TestAucuneErreurServeur:
    """Une 500 est un défaut quel que soit le visiteur, y compris anonyme."""

    def test_visiteur_anonyme(self, client, nom_route):
        reponse = client.get(reverse(nom_route))
        assert reponse.status_code < 500, f"{nom_route} → {reponse.status_code} pour un anonyme"

    @pytest.mark.parametrize("role", [User.Role.ADMIN, User.Role.SECRETARIAT, User.Role.ENSEIGNANT, User.Role.ETUDIANT])
    def test_utilisateur_connecte(self, client, comptes, nom_route, role):
        client.force_login(comptes[role])
        reponse = client.get(reverse(nom_route))
        assert reponse.status_code < 500, f"{nom_route} → {reponse.status_code} pour le rôle « {role} »"


@pytest.mark.django_db
class TestCloisonnementDesPortails:
    """
    Le portail administratif ne s'ouvre pas aux étudiants ni aux enseignants.

    Vérifié route par route plutôt que par sondage : c'est précisément le genre
    de contrôle qu'on croit acquis et qu'une seule vue mal protégée dément.
    """

    @pytest.mark.parametrize("role", [User.Role.ETUDIANT, User.Role.ENSEIGNANT])
    def test_les_pages_du_personnel_sont_fermees(self, client, comptes, role):
        client.force_login(comptes[role])
        fuites = []
        for nom_route in ROUTES:
            if not nom_route.startswith(PREFIXES_PERSONNEL):
                continue
            reponse = client.get(reverse(nom_route))
            if reponse.status_code == 200:
                fuites.append(nom_route)
        assert not fuites, f"Accessibles au rôle « {role} » : {fuites}"

    def test_le_secretariat_n_atteint_pas_le_pilotage(self, client, comptes):
        """Seuls les indicateurs de direction restent fermés au secrétariat."""
        client.force_login(comptes[User.Role.SECRETARIAT])
        assert client.get(reverse("administration:dashboard")).status_code != 200

    def test_l_espace_etudiant_est_ferme_aux_autres(self, client, comptes):
        client.force_login(comptes[User.Role.ENSEIGNANT])
        for nom_route in ("etudiant:dashboard", "etudiant:grades", "documents:list"):
            assert client.get(reverse(nom_route)).status_code != 200, nom_route


@pytest.mark.django_db
class TestPagesPubliques:
    """Les pages ouvertes doivent l'être réellement, sans compte."""

    @pytest.mark.parametrize(
        "nom_route",
        [
            "elearning:catalogue",
            "formations:parcours_list",
            "formations:professeur_list",
            "library:catalogue",
            "admissions:candidature_form",
            "accounts:login",
            "healthz",
        ],
    )
    def test_repondent_sans_authentification(self, client, nom_route):
        assert client.get(reverse(nom_route)).status_code == 200, nom_route


@pytest.mark.django_db
class TestRenduSousStockageDeProduction:
    """
    Les pages doivent se rendre avec le stockage statique de production.

    En production, `ManifestStaticFilesStorage` lève une erreur au rendu si un
    « {% static %} » ne se résout pas. Comme la référence fautive vivait dans
    `base.html`, le défaut aurait mis **tout le site** en erreur 500 — sans
    qu'aucun test, ni la collecte des statiques, ne s'en aperçoive : la
    collecte ne rend pas les gabarits, et les tests utilisent un stockage
    permissif.
    """

    @pytest.fixture(autouse=True)
    def _stockage_manifeste(self, settings, tmp_path):
        from django.contrib.staticfiles.storage import staticfiles_storage
        from django.core.files.storage import storages
        from django.core.management import call_command
        from django.utils.functional import empty

        def reinitialiser():
            # Le registre garde en cache l'instance construite au démarrage :
            # sans purge, le nouveau réglage resterait sans effet.
            storages._storages = {}
            staticfiles_storage._wrapped = empty

        settings.STATIC_ROOT = tmp_path / "statiques"
        settings.STORAGES = {
            **settings.STORAGES,
            "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.ManifestStaticFilesStorage"},
        }
        reinitialiser()
        call_command("collectstatic", verbosity=0, interactive=False)
        yield
        reinitialiser()

    @pytest.mark.parametrize(
        "nom_route",
        ["elearning:catalogue", "formations:parcours_list", "library:catalogue", "accounts:login"],
    )
    def test_les_pages_publiques_se_rendent(self, client, nom_route):
        assert client.get(reverse(nom_route)).status_code == 200, nom_route

    def test_une_page_de_portail_se_rend(self, client, comptes):
        client.force_login(comptes[User.Role.ETUDIANT])
        assert client.get(reverse("etudiant:dashboard")).status_code == 200
