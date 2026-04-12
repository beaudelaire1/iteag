from django.contrib import admin

from .models import Cours, Discipline, Parcours, Professeur, Tarif


@admin.register(Discipline)
class DisciplineAdmin(admin.ModelAdmin):
    list_display = ("nom", "ordre")
    prepopulated_fields = {"slug": ("nom",)}


@admin.register(Parcours)
class ParcoursAdmin(admin.ModelAdmin):
    list_display = ("nom", "type_parcours", "ects_requis", "duree_annees", "actif")
    list_filter = ("type_parcours", "actif")
    prepopulated_fields = {"slug": ("nom",)}


@admin.register(Cours)
class CoursAdmin(admin.ModelAdmin):
    list_display = ("titre", "discipline", "ects", "actif")
    list_filter = ("discipline", "actif")
    search_fields = ("titre",)
    prepopulated_fields = {"slug": ("titre",)}


@admin.register(Professeur)
class ProfesseurAdmin(admin.ModelAdmin):
    list_display = ("nom_complet", "specialite", "actif", "ordre")
    list_filter = ("actif", "disciplines")
    search_fields = ("nom", "prenom")
    prepopulated_fields = {"slug": ("prenom", "nom")}
    filter_horizontal = ("disciplines",)


@admin.register(Tarif)
class TarifAdmin(admin.ModelAdmin):
    list_display = ("formule", "type_membre", "montant_session", "actif")
    list_filter = ("formule", "type_membre")
