from django.contrib import admin

from apps.core.models import AbonneNewsletter, JournalAudit, Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ["titre", "destinataire", "type_notification", "lu", "created_at"]
    list_filter = ["lu", "type_notification", "created_at"]
    search_fields = ["titre", "message", "destinataire__email", "destinataire__last_name"]
    date_hierarchy = "created_at"


@admin.register(JournalAudit)
class JournalAuditAdmin(admin.ModelAdmin):
    """Le journal se consulte et s'exporte, il ne se modifie pas."""

    list_display = ["created_at", "utilisateur", "action", "objet_type", "objet_libelle", "adresse_ip"]
    list_filter = ["action", "objet_type", "created_at"]
    search_fields = ["objet_libelle", "objet_id", "adresse_ip", "utilisateur__email"]
    date_hierarchy = "created_at"
    readonly_fields = [f.name for f in JournalAudit._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        # La purge relève de la tâche planifiée, pas d'une suppression manuelle.
        return False


@admin.register(AbonneNewsletter)
class AbonneNewsletterAdmin(admin.ModelAdmin):
    list_display = ["email", "confirme", "actif", "date_confirmation", "created_at"]
    list_filter = ["confirme", "actif", "created_at"]
    search_fields = ["email"]
    readonly_fields = ["token_confirmation", "token_desinscription", "date_confirmation", "date_desinscription"]
    actions = ["exporter_csv"]

    @admin.action(description="Exporter les abonnés confirmés (CSV)")
    def exporter_csv(self, request, queryset):
        import csv

        from django.http import HttpResponse

        from apps.core.services.audit import journaliser

        reponse = HttpResponse(content_type="text/csv; charset=utf-8")
        reponse["Content-Disposition"] = 'attachment; filename="abonnes-newsletter.csv"'
        redacteur = csv.writer(reponse)
        redacteur.writerow(["email", "date d'inscription", "date de confirmation"])
        confirmes = queryset.filter(confirme=True, actif=True)
        for abonne in confirmes:
            redacteur.writerow(
                [
                    abonne.email,
                    abonne.created_at.strftime("%d/%m/%Y"),
                    abonne.date_confirmation.strftime("%d/%m/%Y") if abonne.date_confirmation else "",
                ]
            )
        journaliser("export", request=request, objet_type="AbonneNewsletter", nombre=confirmes.count())
        return reponse
