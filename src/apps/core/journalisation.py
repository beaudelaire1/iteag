"""
Mise en forme JSON des journaux de production.

Le format était jusqu'ici une chaîne à trous — « {"message":"%(message)s"} ».
Elle produit du JSON tant que le message n'en contient pas les caractères :
un guillemet dans un message d'erreur suffisait à casser la ligne, et une
trace d'exception était émise après l'accolade fermante, en cinq lignes que
l'agrégateur ne rattachait à rien. Autrement dit : le format tenait
exactement tant qu'il ne se passait rien.

Sérialiser un dictionnaire ferme la question sans dépendance nouvelle.
"""

import json
import logging


class JsonFormatter(logging.Formatter):
    """Une ligne, un objet JSON — trace d'exception comprise."""

    def format(self, record: logging.LogRecord) -> str:
        charge = {
            "time": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "name": record.name,
            "message": record.getMessage(),
        }
        # La trace vit dans son propre champ : rattachée à l'événement, et non
        # déversée à sa suite où elle devenait cinq lignes orphelines.
        if record.exc_info:
            charge["exception"] = self.formatException(record.exc_info)
        if record.stack_info:
            charge["stack"] = self.formatStack(record.stack_info)
        # « default=str » : un argument non sérialisable ne doit pas faire
        # perdre la ligne — c'est en général celle qui explique l'incident.
        return json.dumps(charge, ensure_ascii=False, default=str)
