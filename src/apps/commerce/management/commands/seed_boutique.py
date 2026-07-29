"""
Peuple la boutique : livres en vente, commandes et mouvements de stock.

Usage : python manage.py seed_boutique

Les stocks sont volontairement contrastés — un titre épuisé, un sous son seuil
d'alerte, les autres fournis. C'est ce qui rend l'écran de gestion du stock
démonstratif : une liste où tout est vert ne prouve pas que l'alerte marche.

Les commandes couvrent quatre états du cycle, afin que le suivi de commande
montre autre chose qu'une seule ligne « en attente ».
"""

from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from apps.commerce.models import Commande, LigneCommande, MouvementStock, ProduitLivre
from apps.library.models import NoticeBibliographique

# (titre, auteur, sku, isbn, prix, stock, seuil, poids, description)
LIVRES = [
    (
        "Introduction à l'Ancien Testament",
        "Thomas Römer",
        "LIV-AT-001",
        "9782830913682",
        "38.00",
        12,
        3,
        780,
        "Manuel de référence du premier cycle : formation du Pentateuque, livres historiques et prophétiques.",
    ),
    (
        "Introduction au Nouveau Testament",
        "Daniel Marguerat",
        "LIV-NT-001",
        "9782830913804",
        "42.50",
        8,
        3,
        820,
        "Le manuel employé en NT-101 : histoire, théologie et méthodes d'analyse des écrits néotestamentaires.",
    ),
    (
        "Théologie systématique",
        "Wayne Grudem",
        "LIV-TS-001",
        "9782755001570",
        "59.90",
        2,
        3,
        1650,
        "Somme doctrinale en un volume, employée comme ouvrage de fond en théologie systématique.",
    ),
    (
        "L'Évangile selon Jean",
        "Jean Zumstein",
        "LIV-NT-002",
        "9782830915297",
        "45.00",
        6,
        2,
        900,
        "Commentaire exégétique du quatrième évangile, support du cours d'exégèse johannique.",
    ),
    (
        "Histoire du christianisme",
        "Jean Comby",
        "LIV-HE-001",
        "9782204070232",
        "29.00",
        15,
        4,
        540,
        "Des origines à l'époque contemporaine, avec une attention aux missions et au christianisme des Suds.",
    ),
    (
        "Le christianisme dans la Caraïbe",
        "Laënnec Hurbon",
        "LIV-HE-002",
        "9782845860742",
        "26.50",
        0,
        2,
        420,
        "Lecture historique et sociologique du fait chrétien aux Antilles et en Guyane. Épuisé, réédition attendue.",
    ),
    (
        "L'art de prêcher",
        "Haddon Robinson",
        "LIV-TP-001",
        "9782853001281",
        "22.00",
        20,
        5,
        360,
        "Méthode de prédication expositive, ouvrage d'appui du cours de théologie pratique.",
    ),
    (
        "Conduire une Église locale",
        "Alfred Kuen",
        "LIV-TP-002",
        "9782828700683",
        "24.00",
        9,
        3,
        400,
        "Gouvernance, ministères et vie communautaire d'une assemblée locale.",
    ),
    (
        "Concordance biblique Segond 21",
        "Collectif",
        "LIV-OUT-001",
        "9782608123459",
        "48.00",
        4,
        2,
        1400,
        "Outil de travail indispensable pour l'exégèse : concordance complète de la Segond 21.",
    ),
    (
        "Grammaire de l'hébreu biblique",
        "Paul Joüon",
        "LIV-LAN-001",
        "9788876535956",
        "72.00",
        3,
        2,
        1100,
        "Grammaire de référence, employée dans le cursus de langues bibliques.",
    ),
]

# (prénom, nom, email, ville, statut, mode de paiement, articles [(sku, qté)])
COMMANDES = [
    (
        "Josiane",
        "Marceline",
        "josiane.marceline@example.gp",
        "Les Abymes",
        Commande.Statut.LIVREE,
        Commande.ModePaiement.CARTE,
        [("LIV-AT-001", 1), ("LIV-NT-001", 1)],
    ),
    (
        "Emmanuel",
        "Sainte-Rose",
        "emmanuel.sainterose@example.gp",
        "Le Gosier",
        Commande.Statut.EXPEDIEE,
        Commande.ModePaiement.CARTE,
        [("LIV-TS-001", 1)],
    ),
    (
        "Marie-Claire",
        "Bhagavan",
        "mc.bhagavan@example.gf",
        "Cayenne",
        Commande.Statut.CONFIRMEE,
        Commande.ModePaiement.VIREMENT,
        [("LIV-TP-001", 2), ("LIV-HE-001", 1)],
    ),
    (
        "Alexandre",
        "Nordé",
        "alexandre.norde@example.mq",
        "Fort-de-France",
        Commande.Statut.EN_ATTENTE,
        Commande.ModePaiement.VIREMENT,
        [("LIV-NT-002", 1), ("LIV-OUT-001", 1)],
    ),
    (
        "Sylviane",
        "Kancel",
        "sylviane.kancel@example.gp",
        "Baie-Mahault",
        Commande.Statut.EN_ATTENTE,
        Commande.ModePaiement.SUR_PLACE,
        [("LIV-LAN-001", 1)],
    ),
]


class Command(BaseCommand):
    help = "Insère les livres en vente, des commandes dans plusieurs états et le stock correspondant."

    @transaction.atomic
    def handle(self, *args, **options):
        produits = self._seed_livres()
        self._rattacher_notices(produits)
        self._seed_commandes(produits)

        self.stdout.write(
            self.style.SUCCESS(
                f"Boutique : {ProduitLivre.objects.count()} livre(s), {Commande.objects.count()} commande(s)."
            )
        )

    # ── Livres ───────────────────────────────────────────────
    def _seed_livres(self) -> dict[str, ProduitLivre]:
        produits = {}
        for titre, auteur, sku, isbn, prix, stock, seuil, poids, description in LIVRES:
            produit, cree = ProduitLivre.objects.update_or_create(
                sku=sku,
                defaults={
                    "titre": titre,
                    "slug": slugify(titre)[:300],
                    "isbn": isbn,
                    "auteur": auteur,
                    "description": description,
                    "prix_ttc": Decimal(prix),
                    "poids_grammes": poids,
                    "stock_physique": stock,
                    "seuil_alerte": seuil,
                    "actif": True,
                },
            )
            produits[sku] = produit
            if cree and stock:
                MouvementStock.objects.create(
                    produit=produit,
                    type_mouvement=MouvementStock.Type.ENTREE,
                    variation_physique=stock,
                    stock_physique_apres=stock,
                    stock_reserve_apres=produit.stock_reserve,
                    motif="Stock initial (jeu de démonstration)",
                )
        return produits

    def _rattacher_notices(self, produits: dict[str, ProduitLivre]) -> None:
        """Relie chaque livre vendu à sa notice de bibliothèque quand elle existe.

        Le lien est ce qui permet, depuis une notice consultée au catalogue, de
        proposer l'achat — et inversement. Sans lui, les deux catalogues
        s'ignorent alors qu'ils parlent des mêmes ouvrages.
        """
        for produit in produits.values():
            if produit.notice_id:
                continue
            notice = NoticeBibliographique.objects.filter(titre=produit.titre, produit_boutique__isnull=True).first()
            if notice is not None:
                produit.notice = notice
                produit.save(update_fields=["notice", "updated_at"])

    # ── Commandes ────────────────────────────────────────────
    def _seed_commandes(self, produits: dict[str, ProduitLivre]) -> None:
        maintenant = timezone.now()
        for prenom, nom, email, ville, statut, mode, articles in COMMANDES:
            if Commande.objects.filter(email=email).exists():
                continue

            commande = Commande.objects.create(
                prenom=prenom,
                nom=nom,
                email=email,
                telephone="0690 00 00 00",
                adresse="12 rue des Flamboyants",
                code_postal="97139",
                ville=ville,
                statut=statut,
                mode_paiement=mode,
                statut_paiement=(
                    Commande.StatutPaiement.CONFIRME
                    if statut != Commande.Statut.EN_ATTENTE
                    else Commande.StatutPaiement.EN_ATTENTE
                ),
            )

            total = Decimal("0.00")
            for sku, quantite in articles:
                produit = produits[sku]
                ligne_total = produit.prix_ttc * quantite
                LigneCommande.objects.create(
                    commande=commande,
                    produit=produit,
                    sku=produit.sku,
                    titre=produit.titre,
                    prix_unitaire=produit.prix_ttc,
                    quantite=quantite,
                    total_ligne=ligne_total,
                )
                total += ligne_total

            commande.total_produits = total
            commande.frais_livraison = Decimal("0.00")
            commande.total = commande.total_produits + commande.frais_livraison

            # Les dates suivent l'état : une commande livrée sans date
            # d'expédition trahirait le jeu de démonstration au premier clic.
            if statut != Commande.Statut.EN_ATTENTE:
                commande.date_confirmation = maintenant
            if statut in (Commande.Statut.EXPEDIEE, Commande.Statut.LIVREE):
                commande.date_expedition = maintenant
                commande.transporteur = "La Poste — Colissimo"
                commande.numero_suivi = f"6A{commande.numero[-8:]}FR"
            if statut == Commande.Statut.LIVREE:
                commande.date_livraison = maintenant
            commande.save()
