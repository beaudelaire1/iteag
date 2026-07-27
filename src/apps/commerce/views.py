from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import F, Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View
from django.views.generic import DetailView, FormView, ListView, TemplateView

from apps.commerce import panier, services
from apps.commerce.forms import AjouterPanierForm, AjustementStockForm, CommandeForm, ProduitLivreForm
from apps.commerce.models import AlerteStock, Commande, ProduitLivre
from apps.core.mixins import StaffRoleRequiredMixin
from apps.core.services.audit import journaliser


class CatalogueView(ListView):
    model = ProduitLivre
    template_name = "commerce/catalogue.html"
    context_object_name = "produits"
    paginate_by = 12

    def get_queryset(self):
        queryset = ProduitLivre.objects.filter(actif=True).select_related("notice")
        recherche = self.request.GET.get("q", "").strip()
        if recherche:
            queryset = queryset.filter(
                Q(titre__icontains=recherche)
                | Q(auteur__icontains=recherche)
                | Q(isbn__icontains=recherche)
                | Q(sku__icontains=recherche)
            )
        if self.request.GET.get("disponible") == "1":
            queryset = queryset.filter(stock_physique__gt=F("stock_reserve"))
        return queryset

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        contexte["recherche"] = self.request.GET.get("q", "")
        contexte["filtre_disponible"] = self.request.GET.get("disponible") == "1"
        return contexte


class ProduitDetailView(DetailView):
    model = ProduitLivre
    template_name = "commerce/produit_detail.html"
    context_object_name = "produit"

    def get_queryset(self):
        return ProduitLivre.objects.filter(actif=True).select_related("notice")

    def get_context_data(self, **kwargs):
        return {**super().get_context_data(**kwargs), "form": AjouterPanierForm()}


class AjouterPanierView(View):
    http_method_names = ["post"]

    def post(self, request, pk):
        produit = get_object_or_404(ProduitLivre, pk=pk, actif=True)
        formulaire = AjouterPanierForm(request.POST)
        if not formulaire.is_valid():
            messages.error(request, "Indiquez une quantité valide.")
            return redirect(produit)
        try:
            panier.ajouter(request, produit, formulaire.cleaned_data["quantite"])
        except ValueError as erreur:
            messages.error(request, str(erreur))
        else:
            messages.success(request, f"« {produit.titre} » a été ajouté au panier.")
        suivant = request.POST.get("suivant", "")
        if not url_has_allowed_host_and_scheme(
            suivant,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            suivant = reverse("commerce:panier")
        return redirect(suivant)


class ModifierPanierView(View):
    http_method_names = ["post"]

    def post(self, request, pk):
        produit = get_object_or_404(ProduitLivre, pk=pk)
        formulaire = AjouterPanierForm(request.POST)
        quantite = formulaire.cleaned_data["quantite"] if formulaire.is_valid() else 0
        panier.modifier(request, produit, quantite)
        messages.success(request, "Panier mis à jour.")
        return redirect("commerce:panier")


class RetirerPanierView(View):
    http_method_names = ["post"]

    def post(self, request, pk):
        produit = get_object_or_404(ProduitLivre, pk=pk)
        panier.retirer(request, produit)
        messages.success(request, "Livre retiré du panier.")
        return redirect("commerce:panier")


class PanierView(TemplateView):
    template_name = "commerce/panier.html"

    def get_context_data(self, **kwargs):
        lignes, total = panier.details(self.request)
        return {**super().get_context_data(**kwargs), "lignes": lignes, "total": total}


class CommanderView(FormView):
    form_class = CommandeForm
    template_name = "commerce/commander.html"

    def dispatch(self, request, *args, **kwargs):
        self.lignes, self.total_produits = panier.details(request)
        if not self.lignes:
            messages.warning(request, "Votre panier est vide.")
            return redirect("commerce:catalogue")
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        return {**super().get_form_kwargs(), "utilisateur": self.request.user}

    def get_context_data(self, **kwargs):
        frais = getattr(settings, "COMMERCE_FRAIS_LIVRAISON", "0.00")
        return {
            **super().get_context_data(**kwargs),
            "lignes": self.lignes,
            "total_produits": self.total_produits,
            "frais_livraison": frais,
            "total_commande": self.total_produits + Decimal(str(frais)),
        }

    def form_valid(self, form):
        try:
            commande = services.creer_commande(
                donnees=form.cleaned_data,
                lignes_panier=self.lignes,
                utilisateur=self.request.user,
            )
        except ValidationError as erreur:
            form.add_error(None, erreur.messages[0])
            self.lignes, self.total_produits = panier.details(self.request)
            return self.form_invalid(form)
        panier.vider(self.request)
        journaliser("creation", request=self.request, objet=commande, total=str(commande.total))
        messages.success(self.request, f"Votre commande {commande.numero} a bien été enregistrée.")
        return redirect(commande)


class CommandeSuiviView(DetailView):
    model = Commande
    template_name = "commerce/commande_suivi.html"
    context_object_name = "commande"
    slug_field = "jeton_suivi"
    slug_url_kwarg = "jeton"

    def get_queryset(self):
        return Commande.objects.prefetch_related("lignes")


class GestionCommandesView(StaffRoleRequiredMixin, ListView):
    model = Commande
    template_name = "commerce/gestion/commandes.html"
    context_object_name = "commandes"
    paginate_by = 30

    def get_queryset(self):
        queryset = Commande.objects.prefetch_related("lignes")
        statut = self.request.GET.get("statut", "")
        if statut:
            queryset = queryset.filter(statut=statut)
        return queryset

    def get_context_data(self, **kwargs):
        return {
            **super().get_context_data(**kwargs),
            "statuts": Commande.Statut.choices,
            "statut_courant": self.request.GET.get("statut", ""),
            "alertes_stock": AlerteStock.objects.filter(resolue=False).count(),
        }


class CommandeActionView(StaffRoleRequiredMixin, View):
    http_method_names = ["post"]

    def post(self, request, pk):
        commande = get_object_or_404(Commande, pk=pk)
        action = request.POST.get("action")
        try:
            if action == "confirmer":
                commande = services.confirmer_commande(commande, acteur=request.user)
            elif action == "preparer":
                commande = services.preparer_commande(commande)
            elif action == "expedier":
                commande = services.expedier_commande(
                    commande,
                    acteur=request.user,
                    transporteur=request.POST.get("transporteur", ""),
                    numero_suivi=request.POST.get("numero_suivi", ""),
                    url_suivi=request.POST.get("url_suivi_transporteur", ""),
                )
            elif action == "livrer":
                commande = services.livrer_commande(commande)
            elif action == "annuler":
                commande = services.annuler_commande(commande, acteur=request.user)
            else:
                raise ValidationError("Action inconnue.")
        except ValidationError as erreur:
            messages.error(request, erreur.messages[0])
        else:
            journaliser("changement_statut", request=request, objet=commande, statut=commande.statut)
            messages.success(request, f"Commande {commande.numero} : {commande.get_statut_display()}.")
        return redirect("commerce:gestion_commandes")


class GestionStockView(StaffRoleRequiredMixin, ListView):
    model = ProduitLivre
    template_name = "commerce/gestion/stock.html"
    context_object_name = "produits"
    paginate_by = 50

    def get_queryset(self):
        return ProduitLivre.objects.select_related("notice").order_by("titre")

    def get_context_data(self, **kwargs):
        return {
            **super().get_context_data(**kwargs),
            "alertes": AlerteStock.objects.filter(resolue=False).select_related("produit"),
            "form_ajustement": AjustementStockForm(),
        }


class AjusterStockView(StaffRoleRequiredMixin, View):
    http_method_names = ["post"]

    def post(self, request, pk):
        produit = get_object_or_404(ProduitLivre, pk=pk)
        formulaire = AjustementStockForm(request.POST)
        if formulaire.is_valid():
            try:
                produit = services.ajuster_stock(
                    produit,
                    formulaire.cleaned_data["variation"],
                    formulaire.cleaned_data["motif"],
                    acteur=request.user,
                )
            except ValidationError as erreur:
                messages.error(request, erreur.messages[0])
            else:
                journaliser("modification", request=request, objet=produit, stock=produit.stock_physique)
                messages.success(request, f"Stock de « {produit.titre} » mis à jour.")
        else:
            messages.error(request, "Indiquez une variation et un motif valides.")
        return redirect("commerce:gestion_stock")


class ProduitFormMixin(StaffRoleRequiredMixin, FormView):
    form_class = ProduitLivreForm
    template_name = "commerce/gestion/produit_form.html"

    def get_success_url(self):
        return reverse("commerce:gestion_stock")

    def get_context_data(self, **kwargs):
        return {**super().get_context_data(**kwargs), "produit": getattr(self, "produit", None)}


class ProduitCreateView(ProduitFormMixin):
    def form_valid(self, form):
        produit = form.save()
        services.enregistrer_stock_initial(produit, acteur=self.request.user)
        journaliser("creation", request=self.request, objet=produit)
        messages.success(self.request, "Livre ajouté à la boutique.")
        return redirect(self.get_success_url())


class ProduitUpdateView(ProduitFormMixin):
    def dispatch(self, request, *args, **kwargs):
        self.produit = get_object_or_404(ProduitLivre, pk=kwargs["pk"])
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        return {**super().get_form_kwargs(), "instance": self.produit}

    def form_valid(self, form):
        produit = form.save()
        services.synchroniser_alerte_stock(produit)
        journaliser("modification", request=self.request, objet=produit)
        messages.success(self.request, "Livre mis à jour.")
        return redirect(self.get_success_url())
