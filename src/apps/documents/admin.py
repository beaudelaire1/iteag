from django.contrib import admin

from .models import DocumentAdministratif


@admin.register(DocumentAdministratif)
class DocumentAdministratifAdmin(admin.ModelAdmin):
    list_display = ("type_document", "etudiant", "statut_generation", "date_generation")
    list_filter = ("type_document", "statut_generation", "date_generation")
    search_fields = ("etudiant__first_name", "etudiant__last_name", "etudiant__email")
    readonly_fields = ("date_generation", "statut_generation", "erreur_generation", "jeton_generation")
    raw_id_fields = ("etudiant",)
