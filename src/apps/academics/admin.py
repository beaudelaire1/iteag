from django.contrib import admin

from .models import (
    CoursDeSession,
    CreditECTS,
    InscriptionSession,
    Paiement,
    ProfilEtudiant,
    Promotion,
    SessionAcademique,
    Stage,
    VAE,
)


class CreditECTSInline(admin.TabularInline):
    model = CreditECTS
    extra = 0


class InscriptionSessionInline(admin.TabularInline):
    model = InscriptionSession
    extra = 0


class PaiementInline(admin.TabularInline):
    model = Paiement
    extra = 0


@admin.register(Promotion)
class PromotionAdmin(admin.ModelAdmin):
    list_display = ["nom", "parcours", "annee_debut", "annee_fin", "actif"]
    list_filter = ["parcours", "actif"]


@admin.register(ProfilEtudiant)
class ProfilEtudiantAdmin(admin.ModelAdmin):
    list_display = ["utilisateur", "numero_etudiant", "parcours", "promotion", "statut_inscription"]
    list_filter = ["statut_inscription", "parcours", "promotion"]
    search_fields = ["utilisateur__last_name", "utilisateur__first_name", "numero_etudiant"]
    inlines = [CreditECTSInline, InscriptionSessionInline, PaiementInline]


@admin.register(SessionAcademique)
class SessionAcademiqueAdmin(admin.ModelAdmin):
    list_display = ["nom", "periode", "annee_academique", "date_debut", "date_fin", "statut"]
    list_filter = ["statut", "periode", "annee_academique"]


class CoursDeSessionInline(admin.TabularInline):
    model = CoursDeSession
    extra = 1


@admin.register(CoursDeSession)
class CoursDeSessionAdmin(admin.ModelAdmin):
    list_display = ["cours", "session", "enseignant", "statut"]
    list_filter = ["statut", "session"]


@admin.register(Paiement)
class PaiementAdmin(admin.ModelAdmin):
    list_display = ["etudiant", "montant", "date_paiement", "mode", "statut"]
    list_filter = ["statut", "mode"]
    search_fields = ["etudiant__utilisateur__last_name", "reference"]


@admin.register(Stage)
class StageAdmin(admin.ModelAdmin):
    list_display = ["etudiant", "type_stage", "lieu", "date_debut", "date_fin", "statut"]
    list_filter = ["statut"]


@admin.register(VAE)
class VAEAdmin(admin.ModelAdmin):
    list_display = ["etudiant", "ects_demandes", "ects_accordes", "statut"]
    list_filter = ["statut"]
