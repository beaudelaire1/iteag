from django.contrib import admin

from .models import DossierCandidature, HistoriqueStatut


class HistoriqueStatutInline(admin.TabularInline):
    model = HistoriqueStatut
    extra = 0
    readonly_fields = ["ancien_statut", "nouveau_statut", "modifie_par", "commentaire", "created_at"]


@admin.register(DossierCandidature)
class DossierCandidatureAdmin(admin.ModelAdmin):
    list_display = ["nom_complet", "email", "parcours_souhaite", "statut", "date_soumission"]
    list_filter = ["statut", "parcours_souhaite", "eglise_fondatrice"]
    search_fields = ["nom", "prenom", "email"]
    readonly_fields = ["token_suivi", "date_soumission"]
    inlines = [HistoriqueStatutInline]
    fieldsets = [
        ("Identité", {"fields": ["nom", "prenom", "email", "telephone", "date_naissance"]}),
        ("Candidature", {"fields": ["parcours_souhaite", "motivations", "eglise", "eglise_fondatrice"]}),
        ("Pièces jointes", {"fields": ["piece_identite", "diplomes", "autre_document"]}),
        ("Workflow", {"fields": ["statut", "motif_refus", "elements_manquants", "notes_internes"]}),
        ("Suivi", {"fields": ["token_suivi", "date_soumission", "utilisateur_cree"]}),
    ]
