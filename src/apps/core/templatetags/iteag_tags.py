"""Balises de gabarit transverses."""

import random
from urllib.parse import urljoin, urlsplit

from django import template

register = template.Library()


@register.filter
def absolute_url(value, site_url: str) -> str:
    """Rend absolue une URL d'image produite par Django/Wagtail.

    Les stockages locaux renvoient un chemin ``/media/...`` tandis que R2
    renvoie deja une URL HTTPS signee. Les apercus sociaux exigent une URL
    absolue dans les deux cas.
    """
    url = str(value or "").strip()
    if not url:
        return ""
    if urlsplit(url).scheme in {"http", "https"}:
        return url
    return urljoin(f"{str(site_url).rstrip('/')}/", url.lstrip("/"))


# Versets affichés en bandeau. Le tirage se fait côté serveur : le contenu est
# présent dans le HTML livré, donc indexable et lisible sans JavaScript.
VERSETS = [
    (
        "Le commencement de la sagesse, c'est la crainte de l'Éternel ; et la connaissance du Saint, c'est l'intelligence.",
        "Proverbes 9:10",
    ),
    ("Car l'Éternel donne la sagesse ; de sa bouche sortent la connaissance et l'intelligence.", "Proverbes 2:6"),
    ("Mon peuple est détruit, parce qu'il lui manque la connaissance.", "Osée 4:6"),
    (
        "Acquérir la sagesse vaut mieux que l'or, et acquérir l'intelligence est préférable à l'argent.",
        "Proverbes 16:16",
    ),
    ("Heureux l'homme qui a trouvé la sagesse, et l'homme qui possède l'intelligence !", "Proverbes 3:13"),
    (
        "La crainte de l'Éternel est le commencement de la science ; les insensés méprisent la sagesse et l'instruction.",
        "Proverbes 1:7",
    ),
    (
        "Instruis l'enfant selon la voie qu'il doit suivre ; et quand il sera vieux, il ne s'en détournera pas.",
        "Proverbes 22:6",
    ),
    (
        "L'esprit de l'homme éclairé acquiert la connaissance, et l'oreille des sages cherche la science.",
        "Proverbes 18:15",
    ),
    ("La sagesse vaut mieux que les perles, et aucun objet précieux ne l'égale.", "Proverbes 8:11"),
    ("Enseigne-moi le bon sens et l'intelligence, car je crois en tes commandements.", "Psaume 119:66"),
    ("Combien tes paroles sont douces à mon palais, plus que le miel à ma bouche !", "Psaume 119:103"),
    ("L'ouverture de tes paroles éclaire, elle donne de l'intelligence aux simples.", "Psaume 119:130"),
    (
        "Car avec beaucoup de sagesse on a beaucoup de chagrin, et celui qui augmente sa science augmente sa douleur.",
        "Ecclésiaste 1:18",
    ),
    (
        "Car la sagesse protège comme l'argent protège ; mais un avantage de la science, c'est que la sagesse fait vivre ceux qui la possèdent.",
        "Ecclésiaste 7:12",
    ),
    (
        "Oui, si tu appelles la sagesse, et si tu élèves ta voix vers l'intelligence… alors tu comprendras la crainte de l'Éternel.",
        "Proverbes 2:3-5",
    ),
]


@register.simple_tag
def verset_aleatoire():
    """Retourne un verset tiré au sort, sous la forme {texte, reference}."""
    texte, reference = random.choice(VERSETS)  # noqa: S311 — usage décoratif, non cryptographique
    return {"texte": texte, "reference": reference}


@register.simple_tag(takes_context=True)
def lien_page(context, numero) -> str:
    """Adresse de la page `numero`, en conservant les filtres en cours.

    Le gabarit de pagination écrivait « ?page=2 » tout court : passer à la page
    suivante d'une liste filtrée effaçait la recherche et rendait un tout autre
    jeu de résultats, sans le dire.
    """
    requete = context["request"].GET.copy()
    requete["page"] = numero
    return f"?{requete.urlencode()}"
