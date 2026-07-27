from django.contrib import admin

from apps.paiements.models import EvenementStripe, Reglement


@admin.register(Reglement)
class ReglementAdmin(admin.ModelAdmin):
    list_display = ["libelle", "nature", "montant_ttc", "taux_tva", "statut", "contrepartie_delivree", "created_at"]
    list_filter = ["statut", "nature", "contrepartie_delivree"]
    search_fields = ["libelle", "email", "session_stripe", "intention_stripe"]
    date_hierarchy = "created_at"
    # Un règlement est une écriture comptable : il se consulte, il ne se
    # rature pas. Le corriger à la main désynchroniserait le site de Stripe.
    readonly_fields = [
        "nature",
        "module",
        "commande",
        "etudiant",
        "utilisateur",
        "email",
        "libelle",
        "montant_ttc",
        "taux_tva",
        "montant_ht",
        "montant_tva",
        "devise",
        "statut",
        "session_stripe",
        "intention_stripe",
        "date_paiement",
        "date_remboursement",
        "motif_echec",
        "contrepartie_delivree",
    ]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(EvenementStripe)
class EvenementStripeAdmin(admin.ModelAdmin):
    list_display = ["type_evenement", "identifiant", "reglement", "traite", "created_at"]
    list_filter = ["type_evenement", "traite"]
    search_fields = ["identifiant"]
    readonly_fields = ["identifiant", "type_evenement", "reglement", "charge_utile", "traite", "erreur"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
