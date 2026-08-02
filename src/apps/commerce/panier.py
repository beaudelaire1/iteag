"""Panier anonyme conservé dans la session Django."""

from dataclasses import dataclass
from decimal import Decimal

from apps.commerce.models import ProduitLivre

CLE_SESSION = "commerce_panier"


@dataclass(frozen=True)
class LignePanier:
    produit: ProduitLivre
    quantite: int
    total: Decimal


def _brut(request) -> dict[str, int]:
    session = getattr(request, "session", None)
    if session is None:
        return {}

    panier = session.get(CLE_SESSION, {})
    return {str(cle): int(valeur) for cle, valeur in panier.items() if int(valeur) > 0}


def ajouter(request, produit: ProduitLivre, quantite: int = 1) -> int:
    panier = _brut(request)
    cle = str(produit.pk)
    nouvelle = min(panier.get(cle, 0) + max(int(quantite), 1), produit.stock_disponible, 99)
    if nouvelle <= 0:
        raise ValueError("Ce livre n'est plus disponible.")
    panier[cle] = nouvelle
    request.session[CLE_SESSION] = panier
    request.session.modified = True
    return nouvelle


def modifier(request, produit: ProduitLivre, quantite: int) -> None:
    panier = _brut(request)
    cle = str(produit.pk)
    quantite = max(int(quantite), 0)
    if quantite == 0:
        panier.pop(cle, None)
    else:
        panier[cle] = min(quantite, produit.stock_disponible, 99)
        if panier[cle] <= 0:
            panier.pop(cle, None)
    request.session[CLE_SESSION] = panier
    request.session.modified = True


def retirer(request, produit: ProduitLivre) -> None:
    modifier(request, produit, 0)


def vider(request) -> None:
    request.session.pop(CLE_SESSION, None)
    request.session.modified = True


def details(request) -> tuple[list[LignePanier], Decimal]:
    panier = _brut(request)
    produits = {
        str(produit.pk): produit
        for produit in ProduitLivre.objects.filter(pk__in=panier.keys(), actif=True).select_related("notice")
    }
    lignes: list[LignePanier] = []
    total = Decimal("0.00")
    panier_nettoye: dict[str, int] = {}
    for cle, quantite in panier.items():
        produit = produits.get(cle)
        if produit is None or produit.stock_disponible <= 0:
            continue
        quantite = min(quantite, produit.stock_disponible, 99)
        montant = produit.prix_ttc * quantite
        lignes.append(LignePanier(produit=produit, quantite=quantite, total=montant))
        panier_nettoye[cle] = quantite
        total += montant
    if panier_nettoye != panier:
        request.session[CLE_SESSION] = panier_nettoye
        request.session.modified = True
    return lignes, total


def nombre_articles(request) -> int:
    return sum(_brut(request).values())
