from django.contrib import admin

from .models import NoticeBibliographique


@admin.register(NoticeBibliographique)
class NoticeBibliographiqueAdmin(admin.ModelAdmin):
    list_display = ["titre", "auteur", "cote", "discipline", "disponible"]
    list_filter = ["disponible", "discipline"]
    search_fields = ["titre", "auteur", "mots_cles", "cote", "isbn"]
