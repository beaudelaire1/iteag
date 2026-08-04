"""
Les bibliothèques tierces doivent arriver jusqu'à l'image de production.

Le défaut que ce fichier rend impossible à répéter : l'ajout de Quill a mis à
jour le script de copie et le `.gitignore`, mais pas le `Dockerfile.prod`, qui
ne recopiait que `static/js/vendor/`. `static/css/vendor/quill.snow.css`
n'entrait donc jamais dans l'image.

Rien ne le signalait. `collectstatic` ne se plaint pas d'un fichier absent — il
se contente de ne pas l'inscrire au manifeste. La construction passait, l'image
se déployait, et la page de rédaction d'article tombait en 500 au rendu, chez
l'utilisateur :

    ValueError: Missing staticfiles manifest entry for 'css/vendor/quill.snow.css'

Le développement n'en voyait rien : il ne consulte aucun manifeste, et les
fichiers sont présents sur le poste qui vient de lancer « npm run build ».

Trois déclarations doivent donc s'accorder, et c'est ce qui est vérifié ici :
ce que les gabarits réclament, ce que le script produit, ce que l'image emporte.
"""

import re
from pathlib import Path

import pytest
from django.conf import settings

RACINE = Path(settings.BASE_DIR)
SCRIPT_COPIE = RACINE / "scripts" / "copier-vendor.mjs"
DOCKERFILE = RACINE / "Dockerfile.prod"
GABARITS = RACINE / "templates"

# Chemins produits par « npm run vendor:build », tels que le script les déclare.
MOTIF_CIBLE = re.compile(r'"(static/(?:js|css)/vendor/[^"]+)"')
# Références « {% static 'js/vendor/…' %} » dans les gabarits.
MOTIF_STATIC = re.compile(r"""\{%\s*static\s+['"]((?:js|css)/vendor/[^'"]+)['"]""")


def cibles_du_script() -> set[str]:
    contenu = SCRIPT_COPIE.read_text(encoding="utf-8")
    return set(MOTIF_CIBLE.findall(contenu))


def references_des_gabarits() -> dict[str, str]:
    """{chemin statique: gabarit qui le réclame}."""
    trouvees = {}
    for gabarit in GABARITS.rglob("*.html"):
        for chemin in MOTIF_STATIC.findall(gabarit.read_text(encoding="utf-8")):
            trouvees.setdefault(chemin, str(gabarit.relative_to(RACINE)))
    return trouvees


@pytest.fixture(scope="module")
def dockerfile() -> str:
    return DOCKERFILE.read_text(encoding="utf-8")


def test_le_script_de_copie_declare_bien_des_cibles():
    """Un test dont la liste se viderait passerait sans rien vérifier."""
    cibles = cibles_du_script()
    assert len(cibles) >= 3, f"Seulement {len(cibles)} cible(s) lues dans {SCRIPT_COPIE.name}"


def test_chaque_bibliotheque_reclamee_par_un_gabarit_est_produite():
    """Un gabarit ne doit pas réclamer un fichier qu'aucune construction n'écrit."""
    produites = {cible.removeprefix("static/") for cible in cibles_du_script()}
    orphelines = [
        f"{chemin} (réclamé par {gabarit})"
        for chemin, gabarit in sorted(references_des_gabarits().items())
        if chemin not in produites
    ]
    assert not orphelines, "Références sans source dans « scripts/copier-vendor.mjs » :\n  " + "\n  ".join(orphelines)


def test_chaque_bibliotheque_produite_entre_dans_l_image(dockerfile):
    """
    Le cœur du contrôle.

    Ces fichiers sont ignorés par git : s'ils ne sont pas explicitement recopiés
    depuis l'étape de construction, ils n'existent tout simplement pas dans
    l'image finale, et personne ne l'apprend avant le rendu en production.
    """
    absentes = []
    for cible in sorted(cibles_du_script()):
        dossier = f"/app/{Path(cible).parent.as_posix()}/"
        if f"/app/{cible}" not in dockerfile and dossier not in dockerfile:
            absentes.append(cible)

    assert not absentes, (
        "Fichiers produits mais jamais recopiés dans l'image :\n  "
        + "\n  ".join(absentes)
        + f"\n\nAjoutez la ligne « COPY --from=assets /app/<chemin> » dans {DOCKERFILE.name}."
    )


def test_chaque_bibliotheque_produite_est_verifiee_a_la_construction(dockerfile):
    """
    Une copie silencieusement vide vaut une copie absente.

    Le contrôle ne portait que sur « hls.min.js » : c'est ce qui a laissé
    passer l'ajout de Quill sans que la construction ne dise rien.
    """
    non_verifiees = [cible for cible in sorted(cibles_du_script()) if f"test -s {cible}" not in dockerfile]
    assert not non_verifiees, "Fichiers produits sans contrôle « test -s » à la construction :\n  " + "\n  ".join(
        non_verifiees
    )
