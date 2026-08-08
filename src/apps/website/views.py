from django.shortcuts import render


def contact_success(request):
    return render(request, "website/contact_success.html")


def politique_donnees(request):
    """Politique publique, versionnée avec le code et accessible sans compte."""
    return render(request, "website/politique_donnees.html")


def politique_cookies(request):
    """Politique des cookies et stockages locaux réellement utilisés."""
    return render(request, "website/politique_cookies.html")
