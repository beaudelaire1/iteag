from django.contrib import admin

from .models import DocumentAdministratif


@admin.register(DocumentAdministratif)
class DocumentAdministratifAdmin(admin.ModelAdmin):
    list_display = ("type_document", "etudiant", "date_generation")
    list_filter = ("type_document", "date_generation")
    search_fields = ("etudiant__first_name", "etudiant__last_name", "etudiant__email")
    readonly_fields = ("date_generation",)
    raw_id_fields = ("etudiant",)
