"""L'ancienne adresse du secrétariat disparaît de la base, sauf des journaux."""

import importlib
from types import SimpleNamespace

import pytest
from django.apps import apps
from django.db import connection

from apps.accounts.models import User
from apps.formations.models import Professeur

migration = importlib.import_module("apps.website.migrations.0020_effacer_ancienne_adresse_secretariat")
ANCIENNE = migration.ANCIENNE


def _executer():
    migration.effacer_l_ancienne_adresse(apps, SimpleNamespace(connection=connection))


@pytest.mark.django_db
class TestEffacement:
    def test_le_compte_qui_la_porte_perd_son_adresse_sans_prendre_la_boite_gmail(self):
        compte = User.objects.create_user(username="secretariat_iteag", email=ANCIENNE, is_active=False)

        _executer()

        compte.refresh_from_db()
        assert compte.email == ""

    def test_un_texte_redige_pointe_vers_la_boite_gmail(self):
        fiche = Professeur.objects.create(
            nom="Exemple",
            prenom="Fiche",
            slug="fiche-exemple",
            biographie=f"Écrire à {ANCIENNE} pour le joindre.",
        )

        _executer()

        fiche.refresh_from_db()
        assert fiche.biographie == "Écrire à secretariat.iteag@gmail.com pour le joindre."

    def test_une_valeur_json_est_corrigee(self):
        fiche = Professeur.objects.create(
            nom="Exemple", prenom="Json", slug="fiche-json", expertises=["Contact", f"Via {ANCIENNE}"]
        )

        _executer()

        fiche.refresh_from_db()
        assert fiche.expertises == ["Contact", "Via secretariat.iteag@gmail.com"]

    def test_une_base_sans_l_ancienne_adresse_reste_intacte(self):
        fiche = Professeur.objects.create(nom="Exemple", prenom="Intacte", slug="fiche-intacte", biographie="Rien.")

        _executer()

        fiche.refresh_from_db()
        assert fiche.biographie == "Rien."


def test_le_depot_ne_nomme_plus_l_ancienne_adresse_qu_ici():
    """Seule la migration qui l'efface a le droit de la connaître.

    Le dépôt entier est interrogé — code, documentation, CI — par « git grep »
    sur les fichiers suivis : parcourir le disque traverserait node_modules.
    """
    import shutil
    import subprocess
    from pathlib import Path

    git = shutil.which("git")
    if git is None:
        pytest.skip("git est indisponible")
    ici = Path(__file__).resolve()
    # Arguments fixes, aucune saisie extérieure.
    racine = Path(
        subprocess.run(  # noqa: S603
            [git, "rev-parse", "--show-toplevel"], cwd=ici.parent, capture_output=True, text=True, check=True
        ).stdout.strip()
    )
    resultat = subprocess.run([git, "grep", "-l", "-i", "-F", ANCIENNE], cwd=racine, capture_output=True, text=True)  # noqa: S603
    autorises = {Path(migration.__file__).resolve(), ici}
    trouvees = [ligne for ligne in resultat.stdout.splitlines() if (racine / ligne).resolve() not in autorises]
    assert trouvees == []
