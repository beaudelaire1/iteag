from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from apps.core.services.audit import journaliser

from .models import User
from .otp import reinitialiser_second_facteur


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ("username", "email", "first_name", "last_name", "role", "is_active", "last_login")
    list_filter = ("role", "is_active", "is_staff")
    fieldsets = BaseUserAdmin.fieldsets + (("ITEAG", {"fields": ("role", "phone")}),)
    add_fieldsets = BaseUserAdmin.add_fieldsets + (("ITEAG", {"fields": ("role", "phone")}),)
    actions = ["reinitialiser_otp"]

    @admin.action(description="Réinitialiser le second facteur des comptes sélectionnés", permissions=["change"])
    def reinitialiser_otp(self, request, queryset):
        for compte in queryset:
            reinitialiser_second_facteur(compte)
            journaliser(
                "modification",
                request=request,
                objet=compte,
                objet_libelle="Réinitialisation du second facteur",
            )
        self.message_user(
            request,
            "Second facteur réinitialisé. Les comptes soumis à cette vérification "
            "doivent scanner un nouveau QR code à la connexion.",
            level=messages.SUCCESS,
        )
