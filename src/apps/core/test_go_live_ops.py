"""Tests du gate d'exploitation exécuté juste avant la mise en service."""

import ast
import json
import re
import sys
from pathlib import Path

from django.core.management import call_command
from django.test import override_settings
from scripts.verifier_qualifications_zap import verifier_rapport

RACINE = Path(__file__).resolve().parents[2]


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
)
def test_verifier_stockage_media_ecrit_lit_et_supprime(capsys):
    call_command("verifier_stockage_media")

    sortie = capsys.readouterr().out
    assert "écriture, lecture et suppression validées" in sortie


def test_gate_serveur_exige_les_preuves_reelles():
    script = (RACINE / "scripts" / "verifier_go_live.sh").read_text(encoding="utf-8")

    for variable in (
        "GO_LIVE_BASE_URL",
        "GO_LIVE_EMAIL_RECIPIENT",
        "GO_LIVE_BUNNY_VIDEO_ID",
    ):
        assert f"obligatoire {variable}" in script

    assert "python manage.py verifier_production" in script
    assert "python manage.py verifier_heartbeat_celery --max-age 180" in script
    assert "postgres_backup_r2.py status" in script
    assert "postgres_backup_r2.py restore" in script
    assert '--target-db "$GO_LIVE_RESTORE_DB"' in script
    assert "--drop-after" in script
    assert "python manage.py verifier_stockage_media" in script
    assert "python manage.py tester_notifications_email" in script
    assert 'python manage.py verifier_bunny "$GO_LIVE_BUNNY_VIDEO_ID"' in script


def test_gate_serveur_verifie_l_hote_public_et_les_pages_legales():
    """Deux preuves qu'aucun contrôle interne ne peut donner.

    L'application ignore sous quel nom d'hôte le proxy la sert : seule une
    requête depuis l'extérieur peut confronter la balise canonique et le plan
    du site à l'adresse réellement publiée. Et une page légale dépubliée ne
    provoque aucune erreur — il faut aller la demander.
    """
    script = (RACINE / "scripts" / "verifier_go_live.sh").read_text(encoding="utf-8")

    assert "rel=" in script and "canonical" in script
    assert "Le plan du site mêle plusieurs hôtes" in script
    assert "/mentions-legales/" in script
    assert "/conditions-generales-de-vente/" in script


def test_les_blocs_python_du_gate_serveur_compilent():
    """Un script Python inséré dans un fichier shell n'est relu par personne.

    Il n'échoue qu'à l'exécution — c'est-à-dire pendant la bascule, au moment
    où l'on a le moins envie de déboguer une coquille de guillemet.
    """
    script = (RACINE / "scripts" / "verifier_go_live.sh").read_text(encoding="utf-8")

    blocs = re.findall(r"python -c '\n(.*?)\n' ", script, re.S)
    blocs += re.findall(r"<<'PYTHON'\n(.*?)\nPYTHON\n", script, re.S)

    assert blocs, "Aucun bloc Python détecté : l'extraction ne correspond plus au script."
    for bloc in blocs:
        ast.parse(bloc)


def test_le_gate_preprod_n_importe_que_la_bibliotheque_standard():
    """Les audits live exécutent ce script avant d'installer le projet."""
    script = RACINE / "scripts" / "verifier_preprod_deployee.py"
    arbre = ast.parse(script.read_text(encoding="utf-8"), filename=str(script))
    imports: set[str] = set()

    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.Import):
            imports.update(alias.name.split(".", 1)[0] for alias in noeud.names)
        elif isinstance(noeud, ast.ImportFrom) and noeud.module:
            imports.add(noeud.module.split(".", 1)[0])

    externes = imports - set(sys.stdlib_module_names)
    assert not externes, f"Le gate préprod dépend de paquets non disponibles sur un runner vierge : {sorted(externes)}"


def test_compose_exige_une_revision_applicative_sans_masquer_source_commit():
    """Une stack non identifiable ne doit plus pouvoir démarrer silencieusement.

    ``SOURCE_COMMIT`` est une variable prédéfinie par Coolify. La redéclarer
    directement dans Compose peut créer une variable éditable vide. Le contrat
    du projet utilise donc ``ITEAG_REVISION``, configurée dans Coolify avec la
    valeur ``$SOURCE_COMMIT``, et la rend obligatoire avant création des
    conteneurs.
    """
    compose = (RACINE / "docker-compose.prod.yml").read_text(encoding="utf-8")
    ci = (RACINE.parent / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert "ITEAG_REVISION: ${ITEAG_REVISION:?" in compose
    assert "SOURCE_COMMIT:" not in compose
    assert "ITEAG_REVISION: ${{ github.sha }}" in ci


WORKFLOWS_PREDEPLOIEMENT = (
    "predeploy-lighthouse.yml",
    "predeploy-live-audit.yml",
    "predeploy-interactions.yml",
    "predeploy-visual.yml",
    "predeploy-zap.yml",
)


def test_les_controles_live_visent_le_commit_effectivement_deploye():
    """Une URL de préproduction fixe ne doit jamais valider une PR non déployée.

    Les audits live sont déclenchés après un push sur main, puis attendent que
    la préproduction expose exactement le SHA courant avant de commencer. Une
    branche éphémère, une PR ou une ancienne version déjà déployée ne peut donc
    plus produire un faux feu vert.
    """
    for nom in WORKFLOWS_PREDEPLOIEMENT:
        contenu = (RACINE.parent / ".github" / "workflows" / nom).read_text(encoding="utf-8")

        assert "head_ref" not in contenu, nom
        assert "pull_request:" not in contenu, nom
        assert "push:" in contenu, nom
        assert "branches: [main]" in contenu, nom
        assert "schedule:" in contenu, nom
        assert "workflow_dispatch:" in contenu, nom
        assert "verifier_preprod_deployee.py" in contenu, nom
        assert '--revision "$GITHUB_SHA"' in contenu, nom


def test_zap_ne_masque_que_les_alertes_documentees_et_les_url_ciblees():
    """Une qualification ne doit jamais devenir un interrupteur global."""
    configuration = (RACINE.parent / ".github" / "zap-baseline.conf").read_text(encoding="utf-8")
    politique = json.loads((RACINE.parent / ".github" / "zap-qualifications.json").read_text(encoding="utf-8"))
    documentation = (RACINE.parent / "docs" / "exploitation" / "zap-baseline.md").read_text(encoding="utf-8")
    workflow = (RACINE.parent / ".github" / "workflows" / "predeploy-zap.yml").read_text(encoding="utf-8")
    lignes = [
        ligne.split(maxsplit=2)
        for ligne in configuration.splitlines()
        if ligne.strip() and not ligne.lstrip().startswith("#")
    ]

    ignorees = {identifiant for identifiant, action, *_ in lignes if action == "IGNORE"}

    assert (
        ignorees
        == set(politique)
        == {
            "10015",
            "10017",
            "10027",
            "10031",
            "10049",
            "10055",
            "10063",
            "10098",
            "10109",
            "10110",
            "10111",
            "10112",
            "90003",
            "90004",
        }
    )
    assert all(action == "IGNORE" for _, action, *_ in lignes)
    assert all(identifiant != "*" for identifiant, *_ in lignes)
    assert all(identifiant in documentation for identifiant in ignorees)
    assert 'cp "$GITHUB_WORKSPACE/.github/zap-baseline.conf"' in workflow
    assert "-c zap-baseline.conf" in workflow
    assert "verifier_qualifications_zap.py" in workflow
    assert "zap-qualifications.json" in workflow
    assert " -I" not in workflow


def test_qualifications_zap_refusent_une_alerte_hors_surface():
    rapport = {
        "site": [
            {
                "alerts": [
                    {
                        "pluginid": "10031",
                        "instances": [{"uri": "https://preprod.example.org/compte/prive/"}],
                    }
                ]
            }
        ]
    }

    violations = verifier_rapport(
        rapport,
        {"10031": [r"^/contact/"]},
        "https://preprod.example.org",
    )

    assert violations == ["ZAP 10031: URL hors qualification 'https://preprod.example.org/compte/prive/'."]


def test_qualifications_zap_acceptent_une_alerte_sur_la_surface_prouvee():
    rapport = {
        "site": [
            {
                "alerts": [
                    {
                        "pluginid": "10031",
                        "instances": [{"uri": "https://preprod.example.org/contact/?nom=test"}],
                    }
                ]
            }
        ]
    }

    assert (
        verifier_rapport(
            rapport,
            {"10031": [r"^/contact/"]},
            "https://preprod.example.org",
        )
        == []
    )


def test_le_gate_d_accessibilite_couvre_les_pages_publiques_a_formulaire():
    """Le seuil était strict, mais aveugle aux pages où le défaut se trouvait."""
    contenu = (RACINE.parent / ".github" / "workflows" / "predeploy-lighthouse.yml").read_text(encoding="utf-8")

    for chemin in ("/bibliotheque/", "/boutique/", "/e-learning/"):
        assert chemin in contenu, chemin


def test_la_commande_de_readiness_sait_ignorer_la_base():
    """La CI construit l'image sans PostgreSQL : le contrat doit y rester exécutable."""
    ci = (RACINE.parent / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert "verifier_production --sans-base" in ci
