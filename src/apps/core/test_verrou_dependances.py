"""Le verrou des dépendances doit suivre les fichiers qui le déclarent.

Un verrou ne vaut que s'il est à jour. Le défaut qu'il faut empêcher n'est pas
l'oubli du verrou lui-même — on le voit — mais **la dépendance ajoutée sans
régénération** : l'intervalle est dans « base.txt », le paquet manque du
« .lock », et l'image de production part sans lui. L'application démarre en
développement, où la bibliothèque est installée depuis longtemps, et tombe au
déploiement sur un « ModuleNotFoundError » sans rapport visible avec le commit
fautif.

Ce fichier ne vérifie pas la résolution — c'est le travail d'« uv » — mais la
cohérence : tout ce qui est déclaré se retrouve épinglé, et tout est épinglé
avec son empreinte.
"""

import re
from pathlib import Path

import pytest

REQUIREMENTS = Path(__file__).resolve().parents[2] / "requirements"

# « paquet==version », en tête de ligne, dans un fichier de verrou.
EPINGLE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==", re.M)
# « paquet>=1.0,<2.0 » ou « paquet[extra]>=… », dans un fichier de déclaration.
DECLARE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)(?:\[[^\]]*\])?\s*[<>=!~]", re.M)

VERROUS = [("prod", "prod.txt", "prod.lock"), ("dev", "dev.txt", "dev.lock")]


def _normaliser(nom: str) -> str:
    """« PyMuPDF », « pymupdf » et « py_mupdf » désignent le même paquet."""
    return re.sub(r"[-_.]+", "-", nom).lower()


def _lire(nom_fichier: str) -> str:
    return (REQUIREMENTS / nom_fichier).read_text(encoding="utf-8")


def _declares(nom_fichier: str) -> set[str]:
    """Les paquets déclarés, en suivant les « -r » vers les fichiers inclus."""
    texte = _lire(nom_fichier)
    noms = {_normaliser(nom) for nom in DECLARE.findall(texte)}
    for inclus in re.findall(r"^-r\s+(\S+)", texte, re.M):
        noms |= _declares(inclus)
    return noms


@pytest.mark.parametrize(("etiquette", "source", "verrou"), VERROUS, ids=[e for e, _, _ in VERROUS])
def test_tout_ce_qui_est_declare_est_verrouille(etiquette, source, verrou):
    """Une dépendance ajoutée sans régénérer le verrou ne partirait pas en production."""
    manquants = sorted(_declares(source) - {_normaliser(n) for n in EPINGLE.findall(_lire(verrou))})
    assert not manquants, (
        f"Absents de « {verrou} » : {', '.join(manquants)}.\n"
        f"Régénérez-le :\n"
        f"    cd src && python -m uv pip compile requirements/{source} "
        f"--python-version 3.12 --python-platform linux --generate-hashes --no-header "
        f"-o requirements/{verrou}"
    )


@pytest.mark.parametrize(("etiquette", "source", "verrou"), VERROUS, ids=[e for e, _, _ in VERROUS])
def test_chaque_paquet_verrouille_porte_son_empreinte(etiquette, source, verrou):
    """Sans empreinte, pip refuse le fichier entier : le mode vérification est global."""
    texte = _lire(verrou)
    epingles = EPINGLE.findall(texte)
    assert epingles, f"« {verrou} » ne contient aucune version épinglée."
    assert texte.count("--hash=sha256:") >= len(epingles), (
        f"« {verrou} » compte {len(epingles)} paquets pour "
        f"{texte.count('--hash=sha256:')} empreintes : régénérez avec « --generate-hashes »."
    )


@pytest.mark.parametrize(("etiquette", "source", "verrou"), VERROUS, ids=[e for e, _, _ in VERROUS])
def test_le_verrou_dit_pour_quelle_cible_il_a_ete_resolu(etiquette, source, verrou):
    """Un verrou résolu sous Windows en 3.14 n'aurait aucun rapport avec l'image."""
    entete = _lire(verrou)[:1500]
    assert "Python 3.12" in entete and "Linux" in entete, (
        f"« {verrou} » doit rappeler en tête la cible pour laquelle il a été résolu."
    )


def test_la_production_installe_le_verrou_et_pas_les_intervalles():
    """Le Dockerfile est le seul endroit qui décide de ce qui est réellement installé."""
    dockerfile = (REQUIREMENTS.parent / "Dockerfile.prod").read_text(encoding="utf-8")
    assert "requirements/prod.lock" in dockerfile
    assert "--require-hashes" in dockerfile, "Sans ce drapeau, une archive substituée passerait."
    assert "-r requirements/prod.txt" not in dockerfile, "L'image doit installer le verrou, sinon il ne sert à rien."
