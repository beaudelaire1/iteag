"""
Aucune lecture de fichier texte sans encodage explicite.

Le défaut, remonté depuis un poste Windows :

    UnicodeDecodeError: 'charmap' codec can't decode byte 0x9d
    in position 24182: character maps to <undefined>

Sans argument `encoding`, Python emploie l'encodage local. Il vaut UTF-8 sous
Linux et macOS, **cp1252 sous Windows** — où la lecture échoue au premier
caractère hors ASCII. Ce projet est en français : ses gabarits, sa feuille de
style et ses contenus en sont pleins.

La conséquence est qu'un tel défaut est **invisible ici** comme en intégration
continue, tous deux sous Linux. Seul le poste d'un collègue le révèle, et il
le révèle par un plantage, pas par un avertissement.

La règle `PLW1514` en attrape une partie, mais pas les appels dont le chemin
vient d'une variable typée par un retour de fonction — c'est précisément la
forme qui a planté. D'où cette vérification textuelle, qui ne dépend d'aucune
inférence de type.
"""

import re
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parents[2]

# Répertoires parcourus : le code que nous écrivons, pas celui des dépendances.
SOURCES = ["apps", "config", "conftest.py"]

# Appels qui lisent ou écrivent du texte et acceptent un `encoding`.
APPELS = re.compile(r"\.(?:read_text|write_text)\s*\(")

# `open()` en mode binaire n'a pas d'encodage : le repérer pour ne pas le
# signaler à tort.
OUVERTURE_TEXTE = re.compile(r"(?<![\w.])open\s*\(")
MODE_BINAIRE = re.compile(r"""["'][rwax]*b[rwax+]*["']""")


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


def _sans_encodage(ligne: str) -> bool:
    """La ligne ouvre-t-elle un fichier texte sans le dire ?"""
    if "encoding=" in ligne or ligne.lstrip().startswith("#"):
        return False
    if APPELS.search(ligne):
        return True
    if OUVERTURE_TEXTE.search(ligne) and not MODE_BINAIRE.search(ligne):
        # `default_storage.open()` et les fichiers de Django ne prennent pas
        # d'encodage : ce sont des objets de stockage, pas des chemins.
        return not re.search(r"(?:storage|fichier|document|pdf|fitz|Image)\.open\s*\(", ligne)
    return False


FICHIERS = fichiers_python()


def test_le_recensement_trouve_bien_des_fichiers():
    """Un chemin erroné viderait la liste, et le test passerait sans rien vérifier."""
    assert len(FICHIERS) >= 50, f"Seulement {len(FICHIERS)} fichiers recensés"


@pytest.mark.parametrize("fichier", FICHIERS, ids=lambda f: str(f.relative_to(RACINE)))
def test_aucune_lecture_de_texte_sans_encodage(fichier):
    fautifs = [
        f"  {fichier.relative_to(RACINE)}:{numero} → {ligne.strip()}"
        for numero, ligne in enumerate(fichier.read_text(encoding="utf-8").splitlines(), 1)
        if _sans_encodage(ligne)
    ]
    assert not fautifs, (
        "Lecture de fichier texte sans encodage explicite — plantera sous Windows :\n"
        + "\n".join(fautifs)
        + '\n\nAjoutez encoding="utf-8".'
    )


class TestLaGardeElleMeme:
    """Une garde qui ne mord pas est pire qu'aucune garde : elle rassure à tort."""

    @pytest.mark.parametrize(
        "ligne",
        [
            "    texte = chemin.read_text()",
            "    chemin.write_text(contenu)",
            '    with open("fichier.txt") as f:',
            "    return Path(nom).read_text()",
        ],
    )
    def test_elle_repere_les_formes_fautives(self, ligne):
        assert _sans_encodage(ligne)

    @pytest.mark.parametrize(
        "ligne",
        [
            '    texte = chemin.read_text(encoding="utf-8")',
            '    chemin.write_text(contenu, encoding="utf-8")',
            '    with open("fichier.bin", "rb") as f:',
            '    with default_storage.open(cle, "rb") as f:',
            "    donnees = json.loads(contenu)",
        ],
    )
    def test_elle_laisse_passer_les_formes_correctes(self, ligne):
        assert not _sans_encodage(ligne)
