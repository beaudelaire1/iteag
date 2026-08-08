"""Tests du gate d'exploitation exécuté juste avant la mise en service."""

from pathlib import Path

from django.core.management import call_command
from django.test import override_settings

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
