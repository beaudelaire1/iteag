"""Contrôles de configuration propres à la diffusion vidéo."""

from urllib.parse import urlparse

from django.conf import settings
from django.core.checks import Error, Warning, register


@register()
def configuration_diffusion_video(app_configs, **kwargs):
    """Une configuration Bunny invalide ne doit pas produire des lecteurs noirs."""
    if getattr(settings, "ELEARNING_DIFFUSION_VIDEO", "") != "bunny":
        return []

    zone = getattr(settings, "BUNNY_ZONE_DIFFUSION", "")
    cle = getattr(settings, "BUNNY_CLE_SIGNATURE", "")
    if not zone and not cle:
        return [
            Warning(
                "Bunny Stream n'est pas configuré.",
                hint="Renseignez BUNNY_ZONE_DIFFUSION et BUNNY_CLE_SIGNATURE avant d'activer les vidéos protégées.",
                id="elearning.W001",
            )
        ]
    if not zone or not cle:
        return [
            Error(
                "La configuration Bunny Stream est incomplète.",
                hint="La zone de diffusion et la clé de signature doivent être renseignées ensemble.",
                id="elearning.E001",
            )
        ]

    origine = urlparse(zone)
    if origine.scheme != "https" or not origine.hostname or origine.path not in ("", "/"):
        return [
            Error(
                "BUNNY_ZONE_DIFFUSION doit être une origine HTTPS sans chemin.",
                hint="Format attendu : https://vz-xxxx.b-cdn.net",
                id="elearning.E002",
            )
        ]
    return []
