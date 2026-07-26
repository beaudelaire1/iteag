from django.contrib import admin

from .models import (
    VAE,
    CoursDeSession,
    CreditECTS,
    DemandeInscriptionCours,
    HistoriqueDemandeInscription,
    InscriptionSession,
    Paiement,
    ProfilEtudiant,
    Promotion,
    SessionAcademique,
    Stage,
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
    list_display = ["cours", "session", "enseignant", "modalite", "statut", "inscriptions_ouvertes", "capacite"]
    list_filter = ["statut", "modalite", "inscriptions_ouvertes", "session"]


class HistoriqueDemandeInscriptionInline(admin.TabularInline):
    model = HistoriqueDemandeInscription
    extra = 0
    readonly_fields = ["ancien_statut", "nouveau_statut", "modifie_par", "commentaire", "created_at"]
    can_delete = False


@admin.register(DemandeInscriptionCours)
class DemandeInscriptionCoursAdmin(admin.ModelAdmin):
    list_display = ["etudiant", "cours_session", "statut", "montant_du", "paiement", "created_at"]
    list_filter = ["statut", "cours_session__session"]
    search_fields = [
        "etudiant__utilisateur__last_name",
        "etudiant__utilisateur__first_name",
        "etudiant__numero_etudiant",
        "cours_session__cours__titre",
    ]
    inlines = [HistoriqueDemandeInscriptionInline]


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
