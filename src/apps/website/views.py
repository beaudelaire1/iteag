from django.shortcuts import render


def contact_success(request):
    return render(request, "website/contact_success.html")
