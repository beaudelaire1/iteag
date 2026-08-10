"""
Test d'architecture — invariants de dépendance entre applications.

Ces règles sont énoncées dans docs/architecture/uml.md §2.2. Elles ne valent que
si elles sont vérifiées : ce module inspecte le graphe réel des imports et
échoue dès qu'une dépendance non prévue ou circulaire apparaît.

Il n'existe plus de liste de « dette tolérée » : une entorse connue doit être
résorbée dans le code, pas neutralisée dans le test qui est censé la détecter.
"""

import ast
from pathlib import Path

import pytest

APPS_DIR = Path(__file__).resolve().parent.parent

# Dépendances autorisées, app par app. Une app absente de la table ne peut
# dépendre d'aucune autre. Élargir cette table est une décision d'architecture :
# elle se discute, elle ne se subit pas.
DEPENDANCES_AUTORISEES: dict[str, set[str]] = {
    "core": set(),
    "accounts": {"core"},
    "administration": {
        "core",
        "accounts",
        "formations",
        "admissions",
        "academics",
        "library",
        "lms",
        # La fiche de scolarité réunit ce que le secrétariat cherchait dans
        # cinq écrans, documents édités compris. L'arête est ajoutée, et non
        # subie : « documents » ne connaît pas « administration » en retour,
        # donc aucun cycle n'apparaît, et « administration » est déjà le
        # portail qui agrège les domaines — c'est sa raison d'être.
        "documents",
        "elearning",
        # La page de statistiques rend compte de TOUTES les applications :
        # une page de pilotage qui laisserait la boutique et les encaissements
        # hors champ obligerait à ouvrir deux autres écrans pour se faire une
        # idée. Ni « commerce » ni « paiements » ne connaissent
        # « administration » en retour.
        "commerce",
        "paiements",
    },
    "formations": {"core", "library"},
    "admissions": {"core", "formations", "accounts"},
    "academics": {"core", "formations", "accounts"},
    "lms": {"core", "academics", "formations", "library"},
    "elearning": {"core", "accounts", "formations", "academics", "documents"},
    "library": {"core", "formations", "accounts"},
    "commerce": {"core", "accounts", "library"},
    # « paiements » encaisse pour le compte des domaines vendeurs : il les
    # connaît tous les trois, et aucun ne le connaît en retour. Le sens de la
    # flèche est le point important — un domaine qui appellerait le paiement
    # deviendrait indissociable de Stripe.
    "paiements": {"core", "academics", "commerce", "elearning"},
    "documents": {"core", "accounts", "academics"},
    # Les portails agrègent plusieurs domaines : c'est leur raison d'être, et
    # c'est pourquoi ils vivent hors des applications de domaine.
    "portail_etudiant": {"core", "accounts", "formations", "academics", "lms", "documents", "elearning", "library"},
    "portail_enseignant": {"core", "accounts", "formations", "academics", "lms", "elearning"},
    # website est un portail : comme administration, il agrège des domaines.
    # « library » et « commerce » s'y ajoutent pour le plan du site, qui recense
    # les pages publiques des quatre catalogues. Aucun de ces domaines ne
    # connaît « website » en retour : la flèche ne se referme pas.
    #
    # « accounts » s'y ajoute avec les articles de recherche : la soumission
    # d'un article avertit les relecteurs, qui se désignent par leur rôle. Le
    # sens de la flèche reste sain — « accounts » ne connaît que « core ».
    "website": {"core", "accounts", "formations", "elearning", "library", "commerce"},
}


def _apps_presentes() -> set[str]:
    return {chemin.name for chemin in APPS_DIR.iterdir() if chemin.is_dir() and (chemin / "apps.py").exists()}


def _est_module_de_test(chemin: Path) -> bool:
    # `conftest.py` est du montage de test au même titre qu'un `test_*.py` : il
    # n'est jamais importé à l'exécution. L'y inclure ferait apparaître comme
    # dépendance de production ce qu'une simple donnée de test exige.
    return chemin.name in ("tests.py", "conftest.py") or chemin.name.startswith("test_")


def _imports_de_app(app: str) -> set[str]:
    """Applications locales importées par `app`, hors elle-même.

    Les migrations et les modules de test sont écartés : l'invariant porte sur
    le couplage d'exécution. Un test du socle a légitimement besoin de créer un
    utilisateur, sans que cela fasse de `core` un dépendant de `accounts`.
    """
    cibles: set[str] = set()
    for fichier in (APPS_DIR / app).rglob("*.py"):
        if "migrations" in fichier.parts or _est_module_de_test(fichier):
            continue
        arbre = ast.parse(fichier.read_text(encoding="utf-8"), filename=str(fichier))
        for noeud in ast.walk(arbre):
            if isinstance(noeud, ast.ImportFrom) and noeud.module:
                module = noeud.module
            elif isinstance(noeud, ast.Import):
                for alias in noeud.names:
                    module = alias.name
                    if module.startswith("apps."):
                        cibles.add(module.split(".")[1])
                continue
            else:
                continue
            if module.startswith("apps."):
                cibles.add(module.split(".")[1])
    return cibles - {app}


def _graphe() -> dict[str, set[str]]:
    return {app: _imports_de_app(app) for app in sorted(_apps_presentes())}


@pytest.mark.parametrize("app", sorted(_apps_presentes()))
def test_dependances_declarees(app):
    """Aucune app n'importe une app qui ne figure pas dans sa liste autorisée."""
    autorisees = DEPENDANCES_AUTORISEES.get(app)
    assert autorisees is not None, (
        f"L'app « {app} » n'est pas déclarée dans DEPENDANCES_AUTORISEES. "
        "Toute nouvelle app doit y être ajoutée explicitement."
    )
    non_autorisees = _imports_de_app(app) - autorisees
    assert not non_autorisees, (
        f"L'app « {app} » importe {sorted(non_autorisees)}, "
        f"ce que sa déclaration n'autorise pas ({sorted(autorisees) or 'aucune'})."
    )


def test_aucune_entorse_declaree_hors_contrat():
    """Le graphe réel doit être intégralement expliqué par le contrat."""
    entorses = {
        (app, cible)
        for app, cibles in _graphe().items()
        for cible in cibles - DEPENDANCES_AUTORISEES.get(app, set())
    }
    assert not entorses, f"Dépendances hors contrat : {sorted(entorses)}"


def test_core_ne_depend_de_rien():
    """core ne contient que de l'abstrait et du transverse."""
    assert _imports_de_app("core") == set(), "core doit rester sans dépendance vers les autres applications."


def test_graphe_acyclique():
    """Le graphe complet de dépendances ne contient aucun cycle."""
    graphe = _graphe()
    visites: set[str] = set()
    en_cours: list[str] = []

    def descendre(noeud: str):
        if noeud in en_cours:
            cycle = " → ".join([*en_cours[en_cours.index(noeud) :], noeud])
            pytest.fail(f"Dépendance circulaire détectée : {cycle}")
        if noeud in visites:
            return
        en_cours.append(noeud)
        for suivant in sorted(graphe.get(noeud, set())):
            descendre(suivant)
        en_cours.pop()
        visites.add(noeud)

    for app in sorted(graphe):
        descendre(app)


def test_academics_ignore_elearning_et_lms():
    """Le domaine académique ne doit pas relire les moteurs qui lui publient des résultats."""
    imports = _imports_de_app("academics")
    assert "elearning" not in imports, "academics ne doit pas connaître elearning."
    assert "lms" not in imports, "academics ne doit pas connaître lms : le LMS transmet des résultats ECTS au domaine."
