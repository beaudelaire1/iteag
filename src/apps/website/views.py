from django.shortcuts import render


def contact_success(request):
    return render(request, "website/contact_success.html")


def politique_donnees(request):
    """Politique publique, versionnée avec le code et accessible sans compte."""
    return render(request, "website/politique_donnees.html")


def politique_cookies(request):
    """Politique des cookies et stockages locaux réellement utilisés."""
    return render(request, "website/politique_cookies.html")


def mentions_legales(request):
    """Identification de l'éditeur et de l'hébergeur — obligation LCEN art. 6-III.

    Page de code, comme les deux politiques ci-dessus, et non page éditoriale
    Wagtail : un document dont la loi impose la présence ne doit pas pouvoir
    disparaître d'un clic dans l'arborescence, ni rester dépublié sans que la
    chaîne de déploiement s'en aperçoive.
    """
    return render(request, "website/mentions_legales.html")
