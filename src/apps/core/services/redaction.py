"""Assainissement du HTML rédigé dans l'application.

Un enseignant compose son article dans un éditeur visuel : le navigateur envoie
donc du balisage, et ce balisage finit sur une page publique. Sans liste
blanche, un compte compromis — ou une simple copie depuis un site tiers —
suffirait à injecter du script dans une page servie sous le nom de l'institut.

Le principe retenu est celui de la liste blanche stricte : **tout ce qui n'est
pas explicitement autorisé disparaît**. Une liste noire aurait à recenser les
formes d'attaque, dont on n'a jamais la liste complète.

Trois précautions moins évidentes :

- **aucun attribut d'événement**, jamais. `onclick`, `onerror`, `onload` ne
  figurent nulle part dans la liste des attributs autorisés, et nh3 supprime
  d'office ceux qu'il ne connaît pas ;
- **les schémas d'URL sont restreints** à http, https et mailto. Sans cela,
  `href="javascript:…"` passe la validation du balisage tout en exécutant du
  code au clic ;
- **les liens sortants reçoivent `rel="noopener"`**, sinon la page ouverte
  garde une référence sur la nôtre.
"""

from __future__ import annotations

import nh3

# Ce qu'un article de recherche a besoin de porter, et rien de plus.
BALISES = {
    "p",
    "br",
    "strong",
    "b",
    "em",
    "i",
    "u",
    "s",
    "h2",
    "h3",
    "h4",
    "ul",
    "ol",
    "li",
    "blockquote",
    "a",
    "img",
    "figure",
    "figcaption",
    "hr",
    "code",
    "pre",
    "sup",
    "sub",
    "table",
    "thead",
    "tbody",
    "tr",
    "th",
    "td",
}

ATTRIBUTS = {
    "a": {"href", "title"},
    "img": {"src", "alt", "title", "width", "height"},
    "th": {"colspan", "rowspan", "scope"},
    "td": {"colspan", "rowspan"},
}

# « javascript: » et « data: » sont exclus : le premier exécute, le second
# permet d'embarquer un document entier dans un attribut.
SCHEMAS_URL = {"http", "https", "mailto"}


def assainir(html: str | None) -> str:
    """Retourne le HTML débarrassé de tout ce qui n'est pas sur la liste blanche."""
    if not html:
        return ""
    return nh3.clean(
        html,
        tags=BALISES,
        attributes=ATTRIBUTS,
        url_schemes=SCHEMAS_URL,
        link_rel="noopener noreferrer",
    )


def en_texte(html: str | None, limite: int = 0) -> str:
    """Le texte seul, pour un résumé ou une méta-description.

    Sert à fabriquer un extrait sans risquer d'y laisser du balisage ouvert :
    couper du HTML à la main produit des balises non refermées, que le
    navigateur rattrape en avalant le reste de la page.
    """
    texte = " ".join(nh3.clean(html or "", tags=set()).split())
    if limite and len(texte) > limite:
        texte = texte[: limite - 1].rstrip() + "…"
    return texte
