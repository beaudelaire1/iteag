"""
Statistiques transversales de la plateforme.

Le tableau de bord répond à « qu'est-ce qui m'attend aujourd'hui ». Cette page-ci
répond à une autre question, que personne ne peut poser à une liste : « comment
cela évolue ». D'où le parti pris : un bloc par application, et dans chaque bloc
trois façons de lire la même réalité — des compteurs pour l'état, une
répartition pour la structure, une série mensuelle pour la tendance.

Deux règles gouvernent ce fichier, héritées de `pilotage` :

- **aucun indicateur inventé** : ce qui n'est pas saisi n'est pas affiché. La
  bibliothèque n'a pas de modèle d'emprunt, on ne fabrique donc pas de taux de
  rotation ;
- **un dénominateur vide n'est pas zéro** : un taux sans base se rend « — », pas
  « 0 % », qui se lirait comme un échec alors qu'il n'y a rien à mesurer.

Les séries couvrent douze mois glissants, y compris les mois sans activité :
un creux est une information, et le masquer donnerait une courbe qui ment.
"""

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal

from django.db.models import Avg, Count, F, Q, Sum
from django.db.models.functions import TruncMonth
from django.urls import reverse
from django.utils import timezone

from apps.academics.models import (
    CoursDeSession,
    CreditECTS,
    DemandeInscriptionCours,
    InscriptionSession,
    ProfilEtudiant,
)
from apps.accounts.models import User
from apps.admissions.models import DossierCandidature
from apps.commerce.models import Commande, ProduitLivre
from apps.elearning.models import InscriptionModule, ModuleFormation, ProgressionLecon
from apps.formations.models import Cours, Professeur
from apps.library.models import NoticeBibliographique
from apps.paiements.models import Reglement

ZERO = Decimal("0.00")
MOIS_COURTS = (
    "janv.",
    "févr.",
    "mars",
    "avril",
    "mai",
    "juin",
    "juil.",
    "août",
    "sept.",
    "oct.",
    "nov.",
    "déc.",
)


# ══════════════════════════════════════════════
# Formes affichables
# ══════════════════════════════════════════════


@dataclass(frozen=True)
class Indicateur:
    """Un chiffre et ce qu'il veut dire. La précision évite la fausse lecture."""

    libelle: str
    valeur: str
    precision: str = ""


@dataclass(frozen=True)
class Barre:
    """Une ligne de graphique : un libellé, une valeur lisible, une largeur."""

    libelle: str
    texte: str
    part: int


@dataclass(frozen=True)
class Domaine:
    """Un bloc de la page, c'est-à-dire une application de la plateforme."""

    cle: str
    titre: str
    explication: str
    indicateurs: list[Indicateur]
    repartition_titre: str = ""
    repartition: list[Barre] = field(default_factory=list)
    serie_titre: str = ""
    serie: list[Barre] = field(default_factory=list)
    lien_url: str = ""
    lien_libelle: str = ""


# ══════════════════════════════════════════════
# Mise en forme
# ══════════════════════════════════════════════


def _euros(montant) -> str:
    brut = f"{Decimal(montant or 0):,.2f} €"
    return brut.replace(",", " ").replace(".", ",").replace(" ", "\u00a0")


def _nombre(valeur) -> str:
    return f"{int(valeur or 0):,}".replace(",", "\u00a0")


def _pourcent(part, total) -> str:
    """Un taux dont le dénominateur est vide n'existe pas : il se rend « — »."""
    if not total:
        return "—"
    return f"{round(Decimal(part or 0) / Decimal(total) * 100)}\u00a0%"


def _mois_glissants(nombre: int = 12) -> list[date]:
    courant = timezone.localdate().replace(day=1)
    mois, annee, rang = [], courant.year, courant.month
    for _ in range(nombre):
        mois.append(date(annee, rang, 1))
        rang -= 1
        if rang == 0:
            rang, annee = 12, annee - 1
    return list(reversed(mois))


def _libelle_mois(jour: date) -> str:
    return f"{MOIS_COURTS[jour.month - 1]} {jour.year % 100:02d}"


def _barres(couples, *, monnaie: bool = False, limite: int | None = None) -> list[Barre]:
    """Largeur proportionnelle au plus haut de la série, jamais au total.

    Rapporter au total écrase toutes les barres dès qu'une catégorie domine ;
    on ne verrait plus rien des autres, qui sont justement celles à surveiller.
    """
    retenus = list(couples)[:limite] if limite else list(couples)
    valeurs = [Decimal(str(valeur or 0)) for _, valeur in retenus]
    sommet = max(valeurs) if valeurs else ZERO
    return [
        Barre(
            libelle=libelle,
            texte=_euros(valeur) if monnaie else _nombre(valeur),
            part=int(valeur / sommet * 100) if sommet > 0 else 0,
        )
        for (libelle, _), valeur in zip(retenus, valeurs, strict=True)
    ]


def _repartition(queryset, champ: str, libelles: dict | None = None, *, limite: int | None = None) -> list[Barre]:
    lignes = queryset.values(champ).annotate(_nb=Count("id")).order_by("-_nb")
    couples = [((libelles or {}).get(ligne[champ], ligne[champ] or "Non renseigné"), ligne["_nb"]) for ligne in lignes]
    return _barres(couples, limite=limite)


def _serie(queryset, champ_date: str, *, agregat=None, monnaie: bool = False, nombre: int = 12) -> list[Barre]:
    mois = _mois_glissants(nombre)
    lignes = (
        queryset.annotate(_mois=TruncMonth(champ_date))
        .values("_mois")
        .annotate(_valeur=agregat or Count("id"))
        .order_by("_mois")
    )
    releve: dict[date, Decimal] = {}
    for ligne in lignes:
        jour = ligne["_mois"]
        if jour is None:
            continue
        if isinstance(jour, datetime):
            jour = (timezone.localtime(jour) if timezone.is_aware(jour) else jour).date()
        releve[jour.replace(day=1)] = ligne["_valeur"] or 0
    return _barres([(_libelle_mois(jour), releve.get(jour, 0)) for jour in mois], monnaie=monnaie)


# ══════════════════════════════════════════════
# Un bloc par application
# ══════════════════════════════════════════════


def admissions() -> Domaine:
    """Ce que le recrutement produit, et ce qu'il en advient."""
    dossiers = DossierCandidature.objects.all()
    compte = dossiers.aggregate(
        total=Count("id"),
        acceptes=Count("id", filter=Q(statut=DossierCandidature.Statut.ACCEPTE)),
        refuses=Count("id", filter=Q(statut=DossierCandidature.Statut.REFUSE)),
        en_cours=Count(
            "id",
            filter=Q(
                statut__in=[
                    DossierCandidature.Statut.SOUMIS,
                    DossierCandidature.Statut.EN_EXAMEN,
                    DossierCandidature.Statut.INCOMPLET,
                ]
            ),
        ),
    )
    tranches = compte["acceptes"] + compte["refuses"]
    return Domaine(
        cle="admissions",
        titre="Admissions",
        explication="Dossiers de candidature reçus et suite qui leur a été donnée.",
        indicateurs=[
            Indicateur("Dossiers reçus", _nombre(compte["total"]), "depuis l'ouverture"),
            Indicateur("En cours d'instruction", _nombre(compte["en_cours"]), "soumis, en examen ou incomplets"),
            Indicateur("Acceptés", _nombre(compte["acceptes"])),
            Indicateur(
                "Taux d'acceptation",
                _pourcent(compte["acceptes"], tranches),
                f"sur {_nombre(tranches)} dossier(s) tranché(s)",
            ),
        ],
        repartition_titre="Parcours demandés",
        repartition=_repartition(dossiers, "parcours_souhaite__nom", limite=8),
        serie_titre="Dossiers déposés par mois",
        serie=_serie(dossiers, "date_soumission"),
        lien_url=reverse("administration:candidatures"),
        lien_libelle="Voir les candidatures",
    )


def scolarite() -> Domaine:
    """L'effectif étudiant, sa structure et le remplissage de l'offre."""
    etudiants = ProfilEtudiant.objects.all()
    compte = etudiants.aggregate(
        total=Count("id"),
        actifs=Count("id", filter=Q(statut_inscription=ProfilEtudiant.StatutInscription.ACTIF)),
        diplomes=Count("id", filter=Q(statut_inscription=ProfilEtudiant.StatutInscription.DIPLOME)),
    )
    places = CoursDeSession.objects.aggregate(total=Sum("capacite", default=0))["total"] or 0
    occupees = InscriptionSession.objects.count()
    ects = CreditECTS.objects.aggregate(total=Sum("ects_obtenus", default=ZERO))["total"] or ZERO
    return Domaine(
        cle="scolarite",
        titre="Scolarité",
        explication="Effectif inscrit, crédits validés et occupation des cours ouverts.",
        indicateurs=[
            Indicateur("Étudiants", _nombre(compte["total"]), f"dont {_nombre(compte['actifs'])} actif(s)"),
            Indicateur("Diplômés", _nombre(compte["diplomes"])),
            Indicateur("ECTS validés", _nombre(ects), "toutes sources confondues"),
            Indicateur(
                "Remplissage des cours",
                _pourcent(occupees, places),
                f"{_nombre(occupees)} inscription(s) pour {_nombre(places)} place(s)",
            ),
        ],
        repartition_titre="Étudiants par parcours",
        repartition=_repartition(etudiants, "parcours__nom", limite=8),
        serie_titre="Demandes d'inscription à un cours, par mois",
        serie=_serie(DemandeInscriptionCours.objects.all(), "created_at"),
        lien_url=reverse("administration:etudiants"),
        lien_libelle="Voir les étudiants",
    )


def enseignement() -> Domaine:
    """Le catalogue et ceux qui le portent."""
    cours = Cours.objects.all()
    compte = cours.aggregate(
        total=Count("id"),
        actifs=Count("id", filter=Q(actif=True)),
        ects=Sum("ects", filter=Q(actif=True), default=ZERO),
    )
    professeurs = Professeur.objects.aggregate(total=Count("id"), actifs=Count("id", filter=Q(actif=True)))
    offres = CoursDeSession.objects.count()
    return Domaine(
        cle="enseignement",
        titre="Offre de formation",
        explication="Cours du référentiel, volume de crédits proposé et corps enseignant.",
        indicateurs=[
            Indicateur("Cours au catalogue", _nombre(compte["total"]), f"dont {_nombre(compte['actifs'])} actif(s)"),
            Indicateur("ECTS proposés", _nombre(compte["ects"]), "sur les cours actifs"),
            Indicateur("Cours programmés", _nombre(offres), "toutes sessions confondues"),
            Indicateur(
                "Enseignants",
                _nombre(professeurs["total"]),
                f"dont {_nombre(professeurs['actifs'])} en activité",
            ),
        ],
        repartition_titre="Cours par discipline",
        repartition=_repartition(cours, "discipline__nom", limite=10),
        serie_titre="Cours ajoutés au catalogue, par mois",
        serie=_serie(cours, "created_at"),
        lien_url=reverse("administration:courses"),
        lien_libelle="Voir les cours",
    )


def formation_video() -> Domaine:
    """Ce que la plateforme vidéo produit réellement."""
    acces = InscriptionModule.objects.all()
    compte = acces.aggregate(
        total=Count("id"),
        actifs=Count("id", filter=Q(statut=InscriptionModule.StatutAcces.ACTIF)),
        termines=Count("id", filter=Q(statut=InscriptionModule.StatutAcces.TERMINE)),
        avancement=Avg("progression_percent"),
    )
    secondes = ProgressionLecon.objects.aggregate(total=Sum("temps_visionnage_cumule", default=0))["total"] or 0
    publies = ModuleFormation.objects.filter(statut=ModuleFormation.StatutPublication.PUBLIE).count()
    return Domaine(
        cle="formation_video",
        titre="Formation vidéo",
        explication="Accès ouverts aux modules, achèvement et temps réellement visionné.",
        indicateurs=[
            Indicateur("Modules publiés", _nombre(publies)),
            Indicateur("Accès ouverts", _nombre(compte["total"]), f"dont {_nombre(compte['actifs'])} en cours"),
            Indicateur(
                "Taux d'achèvement",
                _pourcent(compte["termines"], compte["total"]),
                f"{_nombre(compte['termines'])} module(s) terminé(s)",
            ),
            Indicateur(
                "Heures visionnées",
                _nombre(round(secondes / 3600)),
                f"avancement moyen {round(compte['avancement'] or 0)} %",
            ),
        ],
        repartition_titre="Origine des accès",
        repartition=_repartition(acces, "source", dict(InscriptionModule.SourceAcces.choices)),
        serie_titre="Accès ouverts par mois",
        serie=_serie(acces, "created_at"),
        lien_url=reverse("administration:video_statistiques"),
        lien_libelle="Détail par module",
    )


def paiements_en_ligne() -> Domaine:
    """Le tunnel de paiement : ce qui aboutit et ce qui se perd en route."""
    reglements = Reglement.objects.all()
    compte = reglements.aggregate(
        payes=Count("id", filter=Q(statut=Reglement.Statut.PAYE)),
        encaisse=Sum("montant_ttc", filter=Q(statut=Reglement.Statut.PAYE), default=ZERO),
        rembourse=Sum("montant_ttc", filter=Q(statut=Reglement.Statut.REMBOURSE), default=ZERO),
        engages=Count(
            "id",
            filter=Q(
                statut__in=[
                    Reglement.Statut.PAYE,
                    Reglement.Statut.ECHOUE,
                    Reglement.Statut.ABANDONNE,
                ]
            ),
        ),
        abandons=Count("id", filter=Q(statut=Reglement.Statut.ABANDONNE)),
    )
    return Domaine(
        cle="paiements",
        titre="Paiements en ligne",
        explication="Règlements par carte, quelle que soit leur nature : module, frais ou commande.",
        indicateurs=[
            Indicateur("Encaissé", _euros(compte["encaisse"]), f"{_nombre(compte['payes'])} règlement(s)"),
            Indicateur(
                "Taux d'aboutissement",
                _pourcent(compte["payes"], compte["engages"]),
                f"{_nombre(compte['abandons'])} abandon(s) en cours de paiement",
            ),
            Indicateur("Panier moyen", _euros(compte["encaisse"] / compte["payes"] if compte["payes"] else ZERO)),
            Indicateur("Remboursé", _euros(compte["rembourse"])),
        ],
        repartition_titre="Nature des règlements aboutis",
        repartition=_repartition(
            reglements.filter(statut=Reglement.Statut.PAYE),
            "nature",
            dict(Reglement.Nature.choices),
        ),
        serie_titre="Montant encaissé par mois",
        serie=_serie(
            reglements.filter(statut=Reglement.Statut.PAYE),
            "date_paiement",
            agregat=Sum("montant_ttc"),
            monnaie=True,
        ),
    )


def boutique() -> Domaine:
    """La librairie : commandes, chiffre d'affaires et stock qui s'épuise."""
    commandes = Commande.objects.all()
    reglees = Q(statut_paiement=Commande.StatutPaiement.CONFIRME)
    compte = commandes.aggregate(
        # L'alias ne peut pas s'appeler « total » : le modèle porte déjà ce champ,
        # et l'agrégat suivant croirait sommer un agrégat.
        nombre=Count("id"),
        reglees=Count("id", filter=reglees),
        chiffre=Sum("total", filter=reglees, default=ZERO),
        a_expedier=Count(
            "id",
            filter=reglees
            & Q(
                statut__in=[
                    Commande.Statut.CONFIRMEE,
                    Commande.Statut.PREPARATION,
                ]
            ),
        ),
    )
    alerte = ProduitLivre.objects.filter(actif=True, stock_physique__lte=F("stock_reserve") + F("seuil_alerte")).count()
    return Domaine(
        cle="boutique",
        titre="Boutique",
        explication="Commandes d'ouvrages, encaissements associés et tension sur les stocks.",
        indicateurs=[
            Indicateur("Commandes", _nombre(compte["nombre"]), f"dont {_nombre(compte['reglees'])} réglée(s)"),
            Indicateur("Chiffre d'affaires", _euros(compte["chiffre"]), "commandes réglées"),
            Indicateur(
                "Panier moyen",
                _euros(compte["chiffre"] / compte["reglees"] if compte["reglees"] else ZERO),
            ),
            Indicateur(
                "À préparer", _nombre(compte["a_expedier"]), f"{_nombre(alerte)} produit(s) sous seuil d'alerte"
            ),
        ],
        repartition_titre="État des commandes",
        repartition=_repartition(commandes, "statut", dict(Commande.Statut.choices)),
        serie_titre="Chiffre d'affaires par mois",
        serie=_serie(commandes.filter(reglees), "created_at", agregat=Sum("total"), monnaie=True),
    )


def bibliotheque() -> Domaine:
    """Le catalogue documentaire.

    Aucun modèle d'emprunt n'existe : on décrit donc le fonds, pas sa
    circulation. Inventer un taux de rotation ici serait un chiffre faux.
    """
    notices = NoticeBibliographique.objects.all()
    compte = notices.aggregate(total=Count("id"), disponibles=Count("id", filter=Q(disponible=True)))
    return Domaine(
        cle="bibliotheque",
        titre="Bibliothèque",
        explication="État du fonds documentaire. Les emprunts ne sont pas encore suivis dans l'application.",
        indicateurs=[
            Indicateur("Notices", _nombre(compte["total"])),
            Indicateur("Disponibles", _nombre(compte["disponibles"])),
            Indicateur(
                "Part disponible",
                _pourcent(compte["disponibles"], compte["total"]),
            ),
            Indicateur(
                "Sans discipline",
                _nombre(notices.filter(discipline__isnull=True).count()),
                "notices non classées",
            ),
        ],
        repartition_titre="Notices par discipline",
        repartition=_repartition(notices, "discipline__nom", limite=10),
        serie_titre="Notices ajoutées par mois",
        serie=_serie(notices, "created_at"),
    )


def comptes() -> Domaine:
    """Qui possède un accès, et qui s'en sert."""
    utilisateurs = User.objects.all()
    recent = timezone.now() - timedelta(days=30)
    compte = utilisateurs.aggregate(
        total=Count("id"),
        actifs=Count("id", filter=Q(is_active=True)),
        connectes=Count("id", filter=Q(last_login__gte=recent)),
        jamais=Count("id", filter=Q(last_login__isnull=True)),
    )
    return Domaine(
        cle="comptes",
        titre="Comptes",
        explication="Accès ouverts à la plateforme et usage réel qui en est fait.",
        indicateurs=[
            Indicateur("Comptes actifs", _nombre(compte["actifs"]), f"sur {_nombre(compte['total'])} créé(s)"),
            Indicateur("Connectés sur 30 jours", _nombre(compte["connectes"])),
            Indicateur("Taux d'usage", _pourcent(compte["connectes"], compte["actifs"]), "comptes actifs sollicités"),
            Indicateur("Jamais connectés", _nombre(compte["jamais"]), "identifiants à relancer"),
        ],
        repartition_titre="Comptes par rôle",
        repartition=_repartition(utilisateurs.filter(is_active=True), "role", dict(User.Role.choices)),
        serie_titre="Comptes créés par mois",
        serie=_serie(utilisateurs, "date_joined"),
        lien_url=reverse("administration:utilisateurs"),
        lien_libelle="Voir les utilisateurs",
    )


def tous_les_domaines() -> list[Domaine]:
    """L'ordre suit le parcours d'un étudiant : il entre, il étudie, il paie."""
    return [
        admissions(),
        scolarite(),
        enseignement(),
        formation_video(),
        paiements_en_ligne(),
        boutique(),
        bibliotheque(),
        comptes(),
    ]
