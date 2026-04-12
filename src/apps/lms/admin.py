from django.contrib import admin

from .models import Annonce, Evaluation, RessourcePedagogique


@admin.register(RessourcePedagogique)
class RessourcePedagogiqueAdmin(admin.ModelAdmin):
    list_display = ["titre", "cours_session", "type_fichier", "visible_etudiants", "created_at"]
    list_filter = ["visible_etudiants", "type_fichier"]
    search_fields = ["titre"]


@admin.register(Evaluation)
class EvaluationAdmin(admin.ModelAdmin):
    list_display = ["etudiant", "cours_session", "type_evaluation", "statut", "note", "ects_valides"]
    list_filter = ["statut", "type_evaluation"]
    search_fields = ["etudiant__utilisateur__last_name"]


@admin.register(Annonce)
class AnnonceAdmin(admin.ModelAdmin):
    list_display = ["titre", "cours_session", "auteur", "created_at"]
    search_fields = ["titre"]
