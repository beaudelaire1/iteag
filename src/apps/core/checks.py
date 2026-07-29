"""
Contrôles de démarrage sur la feuille de style construite.

Pourquoi : `static/css/main.css` est un artefact de compilation, donc ignoré
par git. Récupérer une branche apporte les gabarits mais **pas** les styles.
Le site s'ouvre alors avec un HTML neuf sur des règles anciennes — les
composants introduits depuis n'existent pas, les panneaux de navigation
coulent dans la page, les icônes s'affichent à leur taille intrinsèque.

Rien ne le signalait : ni erreur, ni journal, ni test. Seulement une page
manifestement cassée, dont la cause n'a aucun rapport visible avec l'effet.

La comparaison des dates de modification a été essayée et écartée : Tailwind
n'écrit la sortie que si son contenu change, si bien qu'une construction
parfaitement à jour peut conserver une date antérieure à sa source. Le
contrôle porte donc sur le **contenu** — les composants déclarés dans la
source sont-ils présents dans la feuille servie ? C'est précisément ce qui
manque quand la construction est en retard, et cela ne produit aucune fausse
alerte.
"""

import re
from pathlib import Path

from django.conf import settings
from django.core.checks import Error, Warning, register

COMMANDE = "cd src && npm run build"

# Sélecteurs de classe déclarés en tête de règle dans la couche des composants
# de « input.css » : deux espaces d'indentation, un point, un nom.
DECLARATION = re.compile(r"^\s{2}\.([a-z][a-z0-9-]{3,})[\s,{:]", re.M)


def _chemins() -> tuple[Path, Path]:
    racine = Path(settings.BASE_DIR)
    return racine / "assets" / "css" / "input.css", racine / "static" / "css" / "main.css"


def composants_manquants() -> list[str]:
    """Composants déclarés dans la source et absents de la feuille servie."""
    source, construite = _chemins()
    if not source.exists() or not construite.exists():
        return []
    servie = construite.read_text(encoding="utf-8")
    declares = set(DECLARATION.findall(source.read_text(encoding="utf-8")))
    return sorted(nom for nom in declares if f".{nom}" not in servie)


@register()
def styles_construits(app_configs, **kwargs):
    """La feuille servie existe-t-elle, et porte-t-elle bien tous les composants ?"""
    source, construite = _chemins()

    if not source.exists():
        return []  # dépôt partiel ou exécution hors du projet : rien à dire

    if not construite.exists():
        return [
            Error(
                "La feuille de style construite est absente.",
                hint=(
                    f"« {construite} » est un artefact de compilation, ignoré par git : "
                    f"une récupération de branche ne l'apporte pas.\n"
                    f"Lancez : {COMMANDE}"
                ),
                id="core.E001",
            )
        ]

    manquants = composants_manquants()
    if manquants:
        apercu = ", ".join(manquants[:5])
        reste = f" (et {len(manquants) - 5} autres)" if len(manquants) > 5 else ""
        return [
            Warning(
                "La feuille de style construite est en retard sur sa source.",
                hint=(
                    f"Composants déclarés mais absents des styles servis : {apercu}{reste}.\n"
                    "La mise en page paraîtra cassée sans qu'aucune erreur ne soit levée.\n"
                    f"Lancez : {COMMANDE}"
                ),
                id="core.W001",
            )
        ]

    return []


@register()
def configuration_turnstile(app_configs, **kwargs):
    """Une protection annoncée comme active doit être complètement configurée."""
    if not getattr(settings, "CLOUDFLARE_TURNSTILE_ENABLED", False):
        return []

    manquantes = [
        nom
        for nom in ("CLOUDFLARE_TURNSTILE_SITE_KEY", "CLOUDFLARE_TURNSTILE_SECRET_KEY")
        if not getattr(settings, nom, "")
    ]
    if manquantes:
        return [
            Error(
                "Cloudflare Turnstile est activé sans toutes ses clés.",
                hint=f"Renseignez les variables suivantes : {', '.join(manquantes)}.",
                id="core.E002",
            )
        ]

    if getattr(settings, "CLOUDFLARE_TURNSTILE_TIMEOUT", 0) <= 0:
        return [
            Error(
                "Le délai Siteverify de Cloudflare Turnstile doit être positif.",
                hint="Définissez CLOUDFLARE_TURNSTILE_TIMEOUT à 5 secondes, par exemple.",
                id="core.E003",
            )
        ]

    return []


@register()
def configuration_smtp(app_configs, **kwargs):
    """Un backend SMTP actif doit pouvoir réellement authentifier ses envois."""
    if settings.EMAIL_BACKEND != "django.core.mail.backends.smtp.EmailBackend":
        return []

    manquantes = [
        nom for nom in ("EMAIL_HOST", "EMAIL_HOST_USER", "EMAIL_HOST_PASSWORD") if not getattr(settings, nom, "")
    ]
    if manquantes:
        return [
            Error(
                "Les notifications email sont activées sans configuration SMTP complète.",
                hint=f"Renseignez les variables suivantes : {', '.join(manquantes)}.",
                id="core.E004",
            )
        ]

    if settings.EMAIL_USE_TLS and settings.EMAIL_USE_SSL:
        return [
            Error(
                "EMAIL_USE_TLS et EMAIL_USE_SSL ne peuvent pas être actifs ensemble.",
                hint="Gardez uniquement le mode de sécurité indiqué par le fournisseur SMTP.",
                id="core.E005",
            )
        ]

    return []
