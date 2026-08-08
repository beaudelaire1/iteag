"""
Aucune lecture ou écriture de fichier texte sans encodage explicite.

Le défaut, remonté depuis un poste Windows :

    UnicodeDecodeError: 'charmap' codec can't decode byte 0x9d
    in position 24182: character maps to <undefined>

Sans argument `encoding`, Python emploie l'encodage local. Il vaut UTF-8 sous
Linux et macOS, mais peut être cp1252 sous Windows. Ce projet contient du texte
français : une lecture implicite peut donc fonctionner en CI et planter sur un
poste de développement.

Une première garde parcourait le code ligne par ligne. Elle produisait un faux
positif dès qu'un appel correct était écrit sur plusieurs lignes :

    chemin.read_text(
        encoding="utf-8"
    )

Le contrôle repose désormais sur l'AST Python : il examine l'appel complet,
indépendamment de sa mise en forme.
"""

import ast
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parents[2]

# Répertoires parcourus : le code que nous écrivons, pas celui des dépendances.
SOURCES = ["apps", "config", "conftest.py"]


def fichiers_python() -> list[Path]:
    trouves: list[Path] = []
    for source in SOURCES:
        chemin = RACINE / source
        if chemin.is_file():
            trouves.append(chemin)
        else:
            trouves.extend(f for f in chemin.rglob("*.py") if "migrations" not in f.parts)
    # Ce fichier-ci porte des contre-exemples volontaires : les signaler
    # reviendrait à échouer sur la garde elle-même.
    return sorted(f for f in trouves if f.name != Path(__file__).name)


def _mot_cle(appel: ast.Call, nom: str) -> ast.keyword | None:
    return next((mot for mot in appel.keywords if mot.arg == nom), None)


def _valeur_chaine(noeud: ast.AST | None) -> str | None:
    if isinstance(noeud, ast.Constant) and isinstance(noeud.value, str):
        return noeud.value
    return None


def _appel_texte_sans_encodage(appel: ast.Call) -> bool:
    """Un appel de fichier texte connu omet-il son encodage ?"""
    fonction = appel.func

    if isinstance(fonction, ast.Attribute) and fonction.attr in {"read_text", "write_text"}:
        if _mot_cle(appel, "encoding") is not None:
            return False
        # Path.read_text(encoding, errors) : l'encodage est le premier argument.
        if fonction.attr == "read_text":
            return len(appel.args) < 1
        # Path.write_text(data, encoding, errors, newline) : le premier argument
        # est le contenu ; l'encodage est le second.
        return len(appel.args) < 2

    if not isinstance(fonction, ast.Name) or fonction.id != "open":
        return False

    mode_noeud = appel.args[1] if len(appel.args) >= 2 else None
    mode_kw = _mot_cle(appel, "mode")
    if mode_kw is not None:
        mode_noeud = mode_kw.value
    mode = _valeur_chaine(mode_noeud) or "r"
    if "b" in mode:
        return False

    if _mot_cle(appel, "encoding") is not None:
        return False
    # Signature de open : file, mode, buffering, encoding, ...
    if len(appel.args) >= 4:
        return False
    return True


def lignes_sans_encodage(source: str) -> list[int]:
    """Lignes des appels de fichier texte sans encodage explicite."""
    arbre = ast.parse(source)
    return sorted(
        noeud.lineno for noeud in ast.walk(arbre) if isinstance(noeud, ast.Call) and _appel_texte_sans_encodage(noeud)
    )


FICHIERS = fichiers_python()


def test_le_recensement_trouve_bien_des_fichiers():
    """Un chemin erroné viderait la liste, et le test passerait sans rien vérifier."""
    assert len(FICHIERS) >= 50, f"Seulement {len(FICHIERS)} fichiers recensés"


@pytest.mark.parametrize("fichier", FICHIERS, ids=lambda f: str(f.relative_to(RACINE)))
def test_aucune_lecture_de_texte_sans_encodage(fichier):
    source = fichier.read_text(encoding="utf-8")
    lignes = source.splitlines()
    fautifs = [
        f"  {fichier.relative_to(RACINE)}:{numero} → {lignes[numero - 1].strip()}"
        for numero in lignes_sans_encodage(source)
    ]
    assert not fautifs, (
        "Lecture ou écriture de fichier texte sans encodage explicite — peut planter sous Windows :\n"
        + "\n".join(fautifs)
        + '\n\nAjoutez encoding="utf-8".'
    )


class TestLaGardeElleMeme:
    """Une garde qui ne mord pas est pire qu'aucune garde : elle rassure à tort."""

    @pytest.mark.parametrize(
        "source",
        [
            "texte = chemin.read_text()",
            "chemin.write_text(contenu)",
            'with open("fichier.txt") as fichier:\n    texte = fichier.read()',
            "texte = Path(nom).read_text()",
        ],
    )
    def test_elle_repere_les_formes_fautives(self, source):
        assert lignes_sans_encodage(source)

    @pytest.mark.parametrize(
        "source",
        [
            'texte = chemin.read_text(encoding="utf-8")',
            'chemin.write_text(contenu, encoding="utf-8")',
            'with open("fichier.bin", "rb") as fichier:\n    donnees = fichier.read()',
            'with default_storage.open(cle, "rb") as fichier:\n    donnees = fichier.read()',
            'texte = chemin.read_text(\n    encoding="utf-8"\n)',
            'with open(\n    "fichier.txt",\n    encoding="utf-8",\n) as fichier:\n    texte = fichier.read()',
            "donnees = json.loads(contenu)",
        ],
    )
    def test_elle_laisse_passer_les_formes_correctes(self, source):
        assert not lignes_sans_encodage(source)
