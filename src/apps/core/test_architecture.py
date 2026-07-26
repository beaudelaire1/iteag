"""
Test d'architecture — invariants de dépendance entre applications.

Ces règles sont énoncées dans docs/architecture/uml.md §2.2. Elles ne valent que
si elles sont vérifiées : ce module inspecte le graphe réel des imports et
échoue dès qu'une dépendance non prévue ou circulaire apparaît.
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
        "elearning",
    },
    "formations": {"core"},
    "admissions": {"core", "formations", "accounts"},
    "academics": {"core", "formations", "accounts"},
    "lms": {"core", "academics", "formations"},
    "elearning": {"core", "accounts", "formations", "academics"},
    "library": {"core", "formations"},
    "documents": {"core", "accounts", "academics"},
    # Les portails agrègent plusieurs domaines : c'est leur raison d'être, et
    # c'est pourquoi ils vivent hors des applications de domaine.
    "portail_etudiant": {"core", "accounts", "formations", "academics", "lms", "documents", "elearning"},
    # website est un portail : comme administration, il agrège des domaines.
    "website": {"core", "formations", "elearning"},
}

# ── Dette d'architecture identifiée ──────────────────────────────────────────
# Ces arêtes existent dans le code mais contredisent le modèle cible. Elles
# proviennent du fait que les vues des portails étudiant et enseignant vivent
# encore dans les apps de domaine « academics » et « lms » : le tableau de bord
# étudiant agrège des données de lms et documents, ce qui crée le cycle
# academics ↔ lms.
#
# Résorption prévue : extraction des portails hors des apps de domaine, sur le
# modèle de ce qui a été fait pour « administration ».
#
# Ce jeu ne peut que DIMINUER : test_dette_ne_grandit_pas échoue aussi bien si
# une nouvelle entorse apparaît que si une entorse résorbée y reste déclarée.
DETTE_ARCHITECTURE: set[tuple[str, str]] = {
    # Reste après l'extraction du portail étudiant : le service qui porte les
    # crédits ECTS au dossier lit les évaluations, qui vivent dans « lms ».
    # L'arête « academics → documents » a disparu avec le portail.
    ("academics", "lms"),
}


def _apps_presentes() -> set[str]:
    return {chemin.name for chemin in APPS_DIR.iterdir() if chemin.is_dir() and (chemin / "apps.py").exists()}


def _est_module_de_test(chemin: Path) -> bool:
    return chemin.name == "tests.py" or chemin.name.startswith("test_")


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


def _graphe(avec_dette: bool = True) -> dict[str, set[str]]:
    """Graphe réel des dépendances. `avec_dette=False` retire les arêtes connues."""
    graphe = {app: _imports_de_app(app) for app in sorted(_apps_presentes())}
    if not avec_dette:
        for source, cible in DETTE_ARCHITECTURE:
            graphe.get(source, set()).discard(cible)
    return graphe


def _dette_de(app: str) -> set[str]:
    return {cible for source, cible in DETTE_ARCHITECTURE if source == app}


@pytest.mark.parametrize("app", sorted(_apps_presentes()))
def test_dependances_declarees(app):
    """Aucune app n'importe une app qui ne figure pas dans sa liste autorisée."""
    autorisees = DEPENDANCES_AUTORISEES.get(app)
    assert autorisees is not None, (
        f"L'app « {app} » n'est pas déclarée dans DEPENDANCES_AUTORISEES. "
        "Toute nouvelle app doit y être ajoutée explicitement."
    )
    non_autorisees = _imports_de_app(app) - autorisees - _dette_de(app)
    assert not non_autorisees, (
        f"L'app « {app} » importe {sorted(non_autorisees)}, "
        f"ce que sa déclaration n'autorise pas ({sorted(autorisees) or 'aucune'})."
    )


def test_dette_ne_grandit_pas():
    """Le cliquet : la dette déclarée doit correspondre exactement au réel.

    Une entorse nouvelle fait échouer le test ; une entorse résorbée aussi,
    ce qui oblige à la retirer de la déclaration plutôt qu'à l'oublier.
    """
    reelle = {
        (app, cible) for app, cibles in _graphe().items() for cible in cibles - DEPENDANCES_AUTORISEES.get(app, set())
    }
    apparues = reelle - DETTE_ARCHITECTURE
    resorbees = DETTE_ARCHITECTURE - reelle
    assert not apparues, f"Nouvelles entorses à l'architecture : {sorted(apparues)}"
    assert not resorbees, (
        f"Entorses résorbées mais toujours déclarées : {sorted(resorbees)}. Retirez-les de DETTE_ARCHITECTURE."
    )


def test_core_ne_depend_de_rien():
    """core ne contient que de l'abstrait et du transverse."""
    assert _imports_de_app("core") == set(), "core doit rester sans dépendance vers les autres applications."


def test_graphe_acyclique():
    """Hors dette déclarée, le graphe de dépendances ne contient aucun cycle."""
    graphe = _graphe(avec_dette=False)
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


def test_academics_ignore_elearning():
    """L'inversion de dépendance elearning → academics n'est jamais contournée."""
    assert "elearning" not in _imports_de_app("academics"), (
        "academics ne doit pas connaître elearning : le couplage se fait par "
        "la couche service, pas par un import direct."
    )
