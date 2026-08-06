from django.contrib import admin

from .models import Emprunt, NoticeBibliographique


@admin.register(NoticeBibliographique)
class NoticeBibliographiqueAdmin(admin.ModelAdmin):
    list_display = ["titre", "auteur", "cote", "discipline", "disponible"]
    list_filter = ["disponible", "discipline"]
    search_fields = ["titre", "auteur", "mots_cles", "cote", "isbn"]


@admin.register(Emprunt)
class EmpruntAdmin(admin.ModelAdmin):
    list_display = ["notice", "emprunteur", "statut", "date_retour_prevue", "date_retrait"]
    list_filter = ["statut", "date_retour_prevue"]
    search_fields = ["notice__titre", "emprunteur__username", "emprunteur__email"]
