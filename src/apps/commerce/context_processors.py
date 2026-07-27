from apps.commerce.panier import nombre_articles


def panier_context(request):
    return {"panier_nombre": lambda: nombre_articles(request)}
