"""
Le journal de production doit rester lisible par machine.

Une ligne mal formée n'est pas seulement inesthétique : l'agrégateur la
rejette, et l'incident qu'elle décrivait disparaît au moment précis où on le
cherche. Les cas ci-dessous sont ceux qui cassaient l'ancien format à trous —
un guillemet dans un message Stripe, une trace d'exception.
"""

import json
import logging

from apps.core.journalisation import JsonFormatter


def _ligne(record: logging.LogRecord) -> dict:
    return json.loads(JsonFormatter(datefmt="%Y-%m-%dT%H:%M:%S%z").format(record))


def _record(message: str, *args, exc_info=None) -> logging.LogRecord:
    return logging.LogRecord(
        name="apps.paiements",
        level=logging.ERROR,
        pathname=__file__,
        lineno=1,
        msg=message,
        args=args,
        exc_info=exc_info,
    )


def test_un_guillemet_dans_le_message_ne_casse_pas_la_ligne():
    """Le message réel de Stripe en contient : c'est ce qui a été reproduit."""
    message = 'No such customer: "cus_123"'
    assert _ligne(_record(message))["message"] == message


def test_un_retour_ligne_reste_dans_le_champ():
    ligne = _ligne(_record("Première ligne\nSeconde ligne"))
    assert ligne["message"] == "Première ligne\nSeconde ligne"


def test_les_accents_ne_sont_pas_echappes():
    """Le journal se lit aussi à l'œil : « \\u00e9 » ne rend service à personne."""
    rendu = JsonFormatter().format(_record("Règlement refusé"))
    assert "Règlement refusé" in rendu


def test_les_arguments_sont_interpoles():
    assert _ligne(_record("Notification %s refusée", "evt_1"))["message"] == "Notification evt_1 refusée"


def test_un_argument_non_serialisable_ne_perd_pas_la_ligne():
    class Opaque:
        def __str__(self):
            return "objet opaque"

    assert "objet opaque" in _ligne(_record("Objet : %s", Opaque()))["message"]


def test_une_exception_tient_sur_une_seule_ligne():
    """La trace était émise après l'accolade fermante, en cinq lignes orphelines."""
    try:
        raise ValueError('Échec « inattendu "cité" »')
    except ValueError:
        import sys

        rendu = JsonFormatter().format(_record("Échec du traitement", exc_info=sys.exc_info()))

    assert "\n" not in rendu
    ligne = json.loads(rendu)
    assert ligne["message"] == "Échec du traitement"
    assert "ValueError" in ligne["exception"]
    assert "Traceback" in ligne["exception"]


def test_le_niveau_et_le_journal_sont_nommes():
    ligne = _ligne(_record("Peu importe"))
    assert ligne["level"] == "ERROR"
    assert ligne["name"] == "apps.paiements"
    assert ligne["time"]


def test_la_production_utilise_ce_formateur():
    """Le formateur ne sert à rien s'il n'est pas branché."""
    import importlib
    import os
    from unittest import mock

    with mock.patch.dict(
        os.environ,
        {
            "DJANGO_SECRET_KEY": "cle-de-test-pour-import",
            "DJANGO_ALLOWED_HOSTS": "iteag.test",
            "DATABASE_URL": "sqlite:///journal.sqlite3",
            # Importer les réglages de production ne doit pas ouvrir de session
            # Sentry, fût-ce depuis un « .env » local bien rempli.
            "SENTRY_DSN": "",
        },
    ):
        prod = importlib.import_module("config.settings.prod")

    formateur = prod.LOGGING["formatters"]["json"]
    assert formateur["()"] == "apps.core.journalisation.JsonFormatter"
    assert prod.LOGGING["handlers"]["console"]["formatter"] == "json"
