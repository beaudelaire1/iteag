from django.contrib import admin, messages
from django.core.exceptions import ValidationError

from apps.commerce import services
from apps.commerce.models import AlerteStock, Commande, LigneCommande, MouvementStock, ProduitLivre, TarifLivraison


@admin.register(ProduitLivre)
class ProduitLivreAdmin(admin.ModelAdmin):
    list_display = ["titre", "sku", "prix_ttc", "stock_physique", "stock_reserve", "stock_disponible", "actif"]
    list_filter = ["actif"]
    search_fields = ["titre", "auteur", "sku", "isbn"]
    prepopulated_fields = {"slug": ("titre",)}

    @admin.display(description="Disponible")
    def stock_disponible(self, objet):
        return objet.stock_disponible

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if change:
            services.synchroniser_alerte_stock(obj)
        else:
            services.enregistrer_stock_initial(obj, acteur=request.user)

    def get_readonly_fields(self, request, obj=None):
        if obj:
            return ["stock_physique", "stock_reserve"]
        return ["stock_reserve"]


@admin.register(TarifLivraison)
class TarifLivraisonAdmin(admin.ModelAdmin):
    list_display = [
        "destination",
        "type_livraison",
        "poids_max_grammes",
        "prix_ttc",
        "transporteur",
        "offre",
        "date_effet",
        "actif",
        "updated_at",
    ]
    list_filter = ["destination", "type_livraison", "transporteur", "actif"]
    search_fields = ["offre", "source_url"]
    ordering = ["destination", "type_livraison", "poids_max_grammes"]


class LigneCommandeInline(admin.TabularInline):
    model = LigneCommande
    extra = 0
    can_delete = False
    readonly_fields = ["produit", "sku", "titre", "prix_unitaire", "quantite", "total_ligne"]


@admin.register(Commande)
class CommandeAdmin(admin.ModelAdmin):
    list_display = ["numero", "nom_complet", "statut", "statut_paiement", "total", "created_at"]
    list_filter = ["statut", "statut_paiement", "mode_paiement", "pays", "type_livraison"]
    search_fields = ["numero", "nom", "prenom", "email", "numero_suivi"]
    readonly_fields = [
        "numero",
        "jeton_suivi",
        "stock_sorti",
        "poids_total_grammes",
        "total_produits",
        "frais_livraison",
        "total",
        "date_confirmation",
        "date_expedition",
        "date_livraison",
        "date_annulation",
    ]
    inlines = [LigneCommandeInline]
    actions = ["confirmer", "mettre_en_preparation", "expedier", "marquer_livree", "annuler"]

    @admin.action(description="Confirmer le règlement")
    def confirmer(self, request, queryset):
        self._appliquer(
            request,
            queryset,
            lambda commande: services.confirmer_commande(commande, acteur=request.user),
        )

    @admin.action(description="Passer en préparation")
    def mettre_en_preparation(self, request, queryset):
        self._appliquer(request, queryset, services.preparer_commande)

    @admin.action(description="Marquer expédiée")
    def expedier(self, request, queryset):
        self._appliquer(
            request,
            queryset,
            lambda commande: services.expedier_commande(commande, acteur=request.user),
        )

    @admin.action(description="Marquer livrée")
    def marquer_livree(self, request, queryset):
        self._appliquer(request, queryset, services.livrer_commande)

    @admin.action(description="Annuler et libérer le stock")
    def annuler(self, request, queryset):
        self._appliquer(
            request,
            queryset,
            lambda commande: services.annuler_commande(commande, acteur=request.user),
        )

    def _appliquer(self, request, queryset, service):
        succes = 0
        for commande in queryset:
            try:
                service(commande)
            except ValidationError as erreur:
                self.message_user(request, f"{commande.numero} : {erreur.messages[0]}", level=messages.ERROR)
            else:
                succes += 1
        if succes:
            self.message_user(request, f"{succes} commande(s) mise(s) à jour.", level=messages.SUCCESS)


@admin.register(MouvementStock)
class MouvementStockAdmin(admin.ModelAdmin):
    list_display = [
        "produit",
        "type_mouvement",
        "variation_physique",
        "variation_reserve",
        "stock_physique_apres",
        "stock_reserve_apres",
        "created_at",
    ]
    list_filter = ["type_mouvement"]
    search_fields = ["produit__titre", "produit__sku", "commande__numero", "motif"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(AlerteStock)
class AlerteStockAdmin(admin.ModelAdmin):
    list_display = ["produit", "stock_disponible_detecte", "seuil", "resolue", "created_at", "date_resolution"]
    list_filter = ["resolue"]
    search_fields = ["produit__titre", "produit__sku"]
    readonly_fields = ["produit", "stock_disponible_detecte", "seuil", "created_at", "updated_at"]
