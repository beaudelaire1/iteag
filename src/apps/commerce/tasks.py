from celery import shared_task


@shared_task(name="commerce.verifier_stocks")
def verifier_stocks() -> int:
    from apps.commerce.models import ProduitLivre
    from apps.commerce.services import synchroniser_alerte_stock

    nombre = 0
    for produit in ProduitLivre.objects.filter(actif=True):
        if synchroniser_alerte_stock(produit) is not None:
            nombre += 1
    return nombre
