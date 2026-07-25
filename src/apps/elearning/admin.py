from django.contrib import admin, messages
from django.core.exceptions import ValidationError

from apps.elearning.models import (
    AttestationModule,
    Chapitre,
    InscriptionModule,
    JournalAccesVideo,
    Lecon,
    ModuleFormation,
    ProgressionLecon,
    RegleAccesParcours,
    SousTitre,
    VideoAsset,
)
from apps.elearning.services import octroi


class ChapitreInline(admin.TabularInline):
    model = Chapitre
    extra = 1
    ordering = ["ordre"]


class LeconInline(admin.TabularInline):
    model = Lecon
    extra = 1
    ordering = ["ordre"]
    fields = ["ordre", "titre", "slug", "type_lecon", "video", "duree_secondes", "apercu_gratuit", "obligatoire"]
    prepopulated_fields = {"slug": ("titre",)}


class RegleAccesParcoursInline(admin.TabularInline):
    model = RegleAccesParcours
    extra = 1


class SousTitreInline(admin.TabularInline):
    model = SousTitre
    extra = 1


@admin.register(ModuleFormation)
class ModuleFormationAdmin(admin.ModelAdmin):
    list_display = ["titre", "statut", "politique_acces", "niveau", "duree_minutes", "certifiant", "ordre"]
    list_filter = ["statut", "politique_acces", "niveau", "certifiant", "discipline"]
    search_fields = ["titre", "code", "description"]
    prepopulated_fields = {"slug": ("titre",)}
    filter_horizontal = ["prerequis"]
    inlines = [ChapitreInline, RegleAccesParcoursInline]
    readonly_fields = ["duree_totale_secondes", "date_publication"]
    actions = ["publier_modules", "archiver_modules"]

    @admin.action(description="Publier les modules sélectionnés")
    def publier_modules(self, request, queryset):
        publies, refuses = 0, []
        for module in queryset:
            try:
                module.publier()
                publies += 1
            except ValidationError as erreur:
                refuses.append(f"{module.titre} : {erreur.messages[0]}")
        if publies:
            self.message_user(request, f"{publies} module(s) publié(s).", messages.SUCCESS)
        for motif in refuses:
            self.message_user(request, motif, messages.WARNING)

    @admin.action(description="Archiver les modules sélectionnés")
    def archiver_modules(self, request, queryset):
        nombre = queryset.update(statut=ModuleFormation.StatutPublication.ARCHIVE)
        self.message_user(request, f"{nombre} module(s) archivé(s).", messages.SUCCESS)


@admin.register(Chapitre)
class ChapitreAdmin(admin.ModelAdmin):
    list_display = ["titre", "module", "ordre"]
    list_filter = ["module"]
    inlines = [LeconInline]


@admin.register(Lecon)
class LeconAdmin(admin.ModelAdmin):
    list_display = ["titre", "chapitre", "type_lecon", "duree_secondes", "apercu_gratuit", "obligatoire"]
    list_filter = ["type_lecon", "apercu_gratuit", "obligatoire", "chapitre__module"]
    search_fields = ["titre"]
    prepopulated_fields = {"slug": ("titre",)}


@admin.register(VideoAsset)
class VideoAssetAdmin(admin.ModelAdmin):
    list_display = ["titre", "statut_traitement", "duree_secondes", "backend_stockage", "created_at"]
    list_filter = ["statut_traitement", "backend_stockage"]
    search_fields = ["titre", "nom_origine"]
    readonly_fields = ["cle_stockage", "checksum_sha256", "taille_octets", "message_erreur"]
    inlines = [SousTitreInline]
    actions = ["relancer_preparation"]

    @admin.action(description="Relancer la préparation")
    def relancer_preparation(self, request, queryset):
        from apps.elearning.tasks import preparer_video

        for video in queryset:
            preparer_video.delay(str(video.pk))
        self.message_user(request, f"{queryset.count()} préparation(s) relancée(s).", messages.SUCCESS)


@admin.register(InscriptionModule)
class InscriptionModuleAdmin(admin.ModelAdmin):
    """Le secrétariat administre les accès ici, sans développeur."""

    list_display = ["etudiant", "module", "statut", "source", "progression_percent", "date_fin_acces"]
    list_filter = ["statut", "source", "module", "etudiant__parcours", "etudiant__promotion"]
    search_fields = [
        "etudiant__numero_etudiant",
        "etudiant__utilisateur__last_name",
        "etudiant__utilisateur__email",
        "module__titre",
    ]
    readonly_fields = ["progression_percent", "date_completion", "suspendu_par_propagation"]
    actions = ["action_suspendre", "action_reactiver", "action_revoquer", "action_prolonger_90"]

    @admin.action(description="Suspendre les accès sélectionnés")
    def action_suspendre(self, request, queryset):
        nombre = queryset.update(statut=InscriptionModule.StatutAcces.SUSPENDU)
        self.message_user(request, f"{nombre} accès suspendu(s).", messages.SUCCESS)

    @admin.action(description="Réactiver les accès sélectionnés")
    def action_reactiver(self, request, queryset):
        nombre = queryset.update(statut=InscriptionModule.StatutAcces.ACTIF, suspendu_par_propagation=False)
        self.message_user(request, f"{nombre} accès réactivé(s).", messages.SUCCESS)

    @admin.action(description="Révoquer les accès sélectionnés")
    def action_revoquer(self, request, queryset):
        for inscription in queryset:
            octroi.revoquer(inscription, motif="Révocation depuis l'administration", par=request.user)
        self.message_user(request, f"{queryset.count()} accès révoqué(s).", messages.SUCCESS)

    @admin.action(description="Prolonger de 90 jours")
    def action_prolonger_90(self, request, queryset):
        for inscription in queryset:
            octroi.prolonger(inscription, jours=90, par=request.user)
        self.message_user(request, f"{queryset.count()} accès prolongé(s).", messages.SUCCESS)


@admin.register(ProgressionLecon)
class ProgressionLeconAdmin(admin.ModelAdmin):
    list_display = ["inscription", "lecon", "pourcentage_vu", "termine", "date_derniere_vue"]
    list_filter = ["termine", "lecon__chapitre__module"]
    readonly_fields = [f.name for f in ProgressionLecon._meta.fields]

    def has_add_permission(self, request):
        return False


@admin.register(JournalAccesVideo)
class JournalAccesVideoAdmin(admin.ModelAdmin):
    list_display = ["created_at", "utilisateur", "lecon", "resultat", "adresse_ip"]
    list_filter = ["resultat", "created_at"]
    search_fields = ["utilisateur__email", "adresse_ip"]
    date_hierarchy = "created_at"
    readonly_fields = [f.name for f in JournalAccesVideo._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(AttestationModule)
class AttestationModuleAdmin(admin.ModelAdmin):
    list_display = ["numero", "inscription", "date_emission"]
    search_fields = ["numero", "code_verification", "inscription__etudiant__numero_etudiant"]
    readonly_fields = ["numero", "code_verification", "date_emission"]


@admin.register(RegleAccesParcours)
class RegleAccesParcoursAdmin(admin.ModelAdmin):
    list_display = ["parcours", "module", "obligatoire", "duree_acces_jours", "ordre_recommande"]
    list_filter = ["parcours", "obligatoire"]
