from django.contrib import admin

from .models import Emprunt, NoticeBibliographique, SuspensionBibliotheque


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


@admin.register(SuspensionBibliotheque)
class SuspensionBibliothequeAdmin(admin.ModelAdmin):
    list_display = [
        "emprunteur",
        "jours_retard",
        "jours_suspension",
        "date_debut",
        "date_fin",
        "levee_le",
    ]
    list_filter = ["date_fin", "levee_le"]
    search_fields = [
        "emprunteur__username",
        "emprunteur__email",
        "emprunt__notice__titre",
    ]
    readonly_fields = ["jours_retard", "jours_suspension", "date_debut", "date_fin"]
