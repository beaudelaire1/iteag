"""
Socle typographique et graphique des documents imprimés.

Pourquoi ce module existe. Les gabarits PDF nommaient des polices — EB Garamond,
Liberation — installées **uniquement dans l'image de production**. Générés
ailleurs — poste Windows d'un collègue, machine d'un intégrateur, exécution de
test — WeasyPrint ne les trouvait pas et retombait silencieusement sur un
substitut. Le document imprimé ne ressemblait alors pas à celui qui avait été
validé, sans qu'aucune erreur ne le signale : c'est exactement le genre de
défaut qu'on ne découvre que devant la personne à qui l'on remet le papier.

Les polices sont donc désormais celles du dépôt, désignées par leur chemin sur
le disque. Elles sont livrées avec le code, versionnées avec lui, et rendues
identiques partout — y compris hors conteneur.

Le chemin est passé en « file:// » plutôt qu'en base64 : WeasyPrint lit alors le
fichier une fois, sans gonfler le HTML de 1,9 Mo à chaque document produit.
"""

from functools import lru_cache
from pathlib import Path

from django.conf import settings
from django.contrib.staticfiles import finders

# Identité de l'établissement, en un seul endroit. Ces valeurs figurent sur des
# documents officiels : les dupliquer dans chaque gabarit, c'est se garantir
# qu'un jour l'un d'eux gardera l'ancienne adresse.
INSTITUT = {
    "nom": "Institut de Théologie Évangélique des Antilles et de la Guyane",
    "sigle": "ITEAG",
    "adresse": "201 lot Pointe d'Or, 97139 Les Abymes, Guadeloupe",
    "telephone": "+590 690 37 64 17",
    "email": "secretariat@iteag.org",
    "site": "iteag.org",
    "statut": "Association loi 1905",
}

# Fichier du dépôt → nom de famille et graisse déclarés dans « @font-face ».
POLICES = [
    ("fonts/PlayfairDisplay-400.ttf", "Playfair Display", 400, "normal"),
    ("fonts/PlayfairDisplay-700.ttf", "Playfair Display", 700, "normal"),
    ("fonts/PlayfairDisplay-Italic-400.ttf", "Playfair Display", 400, "italic"),
    ("fonts/Inter-400.ttf", "Inter", 400, "normal"),
    ("fonts/Inter-500.ttf", "Inter", 500, "normal"),
    ("fonts/Inter-600.ttf", "Inter", 600, "normal"),
    ("fonts/Inter-700.ttf", "Inter", 700, "normal"),
]

# Les documents administratifs n'emploient ni le romain 400 ni l'italique de
# Playfair Display. Ne pas les déclarer évite à WeasyPrint de lire et analyser
# deux fichiers supplémentaires à chaque génération, sans changer un seul
# glyphe du document.
POLICES_DOCUMENT_ADMINISTRATIF = {
    ("Playfair Display", 700, "normal"),
    ("Inter", 400, "normal"),
    ("Inter", 600, "normal"),
    ("Inter", 700, "normal"),
}

LOGO = "img/logo.png"


def _uri(chemin_statique: str) -> str:
    """Adresse « file:// » d'un fichier statique, ou chaîne vide s'il manque.

    `finders.find` interroge les répertoires de source, pas `STATIC_ROOT` : le
    fichier est donc trouvé avant même un `collectstatic`, et sans dépendre du
    manifeste de production ni d'un aller-retour HTTP du serveur vers lui-même.
    """
    trouve = finders.find(chemin_statique)
    if trouve:
        return Path(trouve).resolve().as_uri()

    repli = Path(settings.STATIC_ROOT or "") / chemin_statique
    return repli.resolve().as_uri() if repli.exists() else ""


@lru_cache(maxsize=2)
def polices_embarquees(profil: str = "complet") -> list[dict]:
    """Déclarations « @font-face » des polices réellement présentes.

    Une police absente est omise plutôt que déclarée : une règle qui pointe
    dans le vide fait retomber WeasyPrint sur un substitut sans rien dire,
    ce qui est précisément le défaut que ce module corrige.
    """
    declarations = []
    for chemin, famille, graisse, style in POLICES:
        if (
            profil == "document_administratif"
            and (
                famille,
                graisse,
                style,
            )
            not in POLICES_DOCUMENT_ADMINISTRATIF
        ):
            continue
        uri = _uri(chemin)
        if uri:
            declarations.append({"uri": uri, "famille": famille, "graisse": graisse, "style": style})
    return declarations


# Bleu de la charte. Le logo livré est blanc sur fond transparent — pensé pour
# un bandeau sombre. Posé tel quel sur le crème d'un document imprimé, il
# disparaît : on ne voyait qu'un halo. Il est donc recoloré pour le papier.
ENCRE_LOGO = (20, 36, 61)


@lru_cache(maxsize=1)
def logo_uri() -> str:
    """Logo encré pour l'impression, en data URI.

    Recoloré depuis le canal alpha du fichier d'origine plutôt que dupliqué en
    seconde image : une marque livrée deux fois finit par diverger, et c'est
    toujours la version imprimée qui reste en retard.
    """
    chemin = finders.find(LOGO)
    if not chemin:
        return ""

    try:
        return _encrer(Path(chemin))
    except Exception:  # noqa: BLE001 — un document sans logo vaut mieux qu'aucun document
        return Path(chemin).resolve().as_uri()


def _encrer(chemin: Path) -> str:
    """Applique l'encre de la charte en conservant la transparence d'origine."""
    import base64
    import io

    from PIL import Image

    with Image.open(chemin) as source:
        alpha = source.convert("RGBA").getchannel("A")
        encre = Image.new("RGBA", source.size, (*ENCRE_LOGO, 255))
        encre.putalpha(alpha)

        tampon = io.BytesIO()
        encre.save(tampon, format="PNG")

    return "data:image/png;base64," + base64.b64encode(tampon.getvalue()).decode()


def qr_data_uri(contenu: str, taille: int = 5) -> str:
    """QR encodé en base64. Aucun appel réseau : un document s'imprime hors ligne."""
    import base64
    import io

    import qrcode

    image = qrcode.make(contenu, box_size=taille, border=1)
    tampon = io.BytesIO()
    image.save(tampon, format="PNG")
    return "data:image/png;base64," + base64.b64encode(tampon.getvalue()).decode()


def contexte_marque(*, profil_polices: str = "complet", **extra) -> dict:
    """Contexte commun à tous les documents imprimés."""
    return {
        "institut": INSTITUT,
        "polices_pdf": polices_embarquees(profil_polices),
        "logo_pdf": logo_uri(),
        **extra,
    }
