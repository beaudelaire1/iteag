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

import re

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
    "h5",
    "h6",
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

# Les anciens contenus Quill expriment l'alignement et le retrait par des
# classes. Elles restent filtrées nom par nom pendant la transition vers
# Draftail : autoriser ``class`` sans limite ouvrirait le design public.
CLASSES_ALIGNEMENT = {"ql-align-center", "ql-align-right", "ql-align-justify"}
CLASSES_ALIGNEMENT_DRAFTAIL = {
    "iteag-align-left",
    "iteag-align-center",
    "iteag-align-right",
    "iteag-align-justify",
}
CLASSES_RETRAIT = {f"ql-indent-{niveau}" for niveau in range(1, 9)}
CLASSES_QUILL = CLASSES_ALIGNEMENT | CLASSES_RETRAIT
CLASSES_TEXTE_RICHE = CLASSES_QUILL | CLASSES_ALIGNEMENT_DRAFTAIL
CLASSES_AUTORISEES = {balise: CLASSES_TEXTE_RICHE for balise in ("p", "h2", "h3", "h4", "h5", "h6", "li", "blockquote")}

# « javascript: » et « data: » sont exclus : le premier exécute, le second
# permet d'embarquer un document entier dans un attribut.
SCHEMAS_URL = {"http", "https", "mailto"}


# Quill 2 encode **toutes** les listes en « <ol> », la puce étant portée par un
# attribut « data-list » sur chaque « <li> », et décore chaque item d'un
# « <span class="ql-ui"> ». Or ni cet attribut ni ce « span » ne sont sur la
# liste blanche : sans normalisation préalable, toute liste à puces ressortirait
# numérotée. Le défaut est silencieux — le texte est là, seule la sémantique a
# changé — et ne se voit qu'à la lecture de l'article publié.
_DECORATION_QUILL = re.compile(r'<span class="ql-ui"[^>]*>\s*</span>')
_LISTE = re.compile(r"<ol>(.*?)</ol>", re.S)
_ITEM = re.compile(r"<li(?P<attributs>[^>]*)>(?P<contenu>.*?)</li>", re.S)
_ATTRIBUT_CLASSES = re.compile(r"""\bclass\s*=\s*(?:"(?P<double>[^"]*)"|'(?P<simple>[^']*)')""", re.I)


def _classes_quill(attributs: str) -> str:
    """Ne conserve que les classes de mise en forme produites par Quill."""
    correspondance = _ATTRIBUT_CLASSES.search(attributs)
    if not correspondance:
        return ""
    valeur = correspondance.group("double") or correspondance.group("simple") or ""
    return " ".join(classe for classe in valeur.split() if classe in CLASSES_QUILL)


def _normaliser_listes(html: str) -> str:
    """Rend aux listes à puces leur « <ul> », que Quill n'écrit jamais.

    Quill encode aussi les niveaux de retrait dans une classe sur le ``li``.
    Cette information est conservée pendant la conversion ``ol``/``ul`` puis
    filtrée une seconde fois par la liste blanche de ``nh3``.
    """

    def refaire(correspondance: re.Match) -> str:
        items = list(_ITEM.finditer(correspondance.group(1)))
        if not items:
            return correspondance.group(0)

        morceaux, groupe_courant, balise_courante = [], [], None
        for item in items:
            balise = "ul" if 'data-list="bullet"' in item.group("attributs") else "ol"
            if balise != balise_courante and groupe_courant:
                morceaux.append(f"<{balise_courante}>{''.join(groupe_courant)}</{balise_courante}>")
                groupe_courant = []
            balise_courante = balise
            classes = _classes_quill(item.group("attributs"))
            attribut_classes = f' class="{classes}"' if classes else ""
            groupe_courant.append(f"<li{attribut_classes}>{item.group('contenu')}</li>")
        if groupe_courant:
            morceaux.append(f"<{balise_courante}>{''.join(groupe_courant)}</{balise_courante}>")
        return "".join(morceaux)

    return _LISTE.sub(refaire, _DECORATION_QUILL.sub("", html))


def assainir(html: str | None) -> str:
    """Retourne le HTML débarrassé de tout ce qui n'est pas sur la liste blanche."""
    if not html:
        return ""
    return nh3.clean(
        _normaliser_listes(html),
        tags=BALISES,
        attributes=ATTRIBUTS,
        allowed_classes=CLASSES_AUTORISEES,
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
