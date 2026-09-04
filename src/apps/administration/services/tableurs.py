"""Ce que le secrétariat peut importer et exporter, entité par entité.

Le moteur — lecture CSV et Excel, écriture, gabarits — vit dans
« core/services/tableur.py » et ne connaît aucun domaine. Ce module déclare les
colonnes, ce qu'elles attendent, et comment une ligne devient un objet.

Deux règles gouvernent tous les imports :

- **une clé naturelle par entité** (numéro étudiant, code de cours, ISBN…). Un
  import est presque toujours une mise à jour d'un fichier existant : sans clé,
  chaque dépôt recrée des doublons que personne ne détecte avant l'inventaire ;
- **tout ou rien.** Une seule ligne fautive annule l'ensemble. Un import à
  moitié appliqué laisse un fichier dont on ne sait plus quelle moitié est à
  jour — plus coûteux à réparer qu'un import refusé.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.utils.text import slugify

from apps.academics.models import ProfilEtudiant, Promotion
from apps.core.services.tableur import Colonne, Schema
from apps.formations.models import Cours, Discipline, Parcours, Professeur
from apps.library.models import NoticeBibliographique


def _exiger(ligne: dict[str, str], champ: str) -> str:
    valeur = (ligne.get(champ) or "").strip()
    if not valeur:
        raise ValidationError(f"La colonne « {champ} » est obligatoire.")
    return valeur


def _decimal(ligne: dict[str, str], champ: str, defaut: str = "0") -> Decimal:
    brut = (ligne.get(champ) or "").strip().replace(",", ".") or defaut
    try:
        return Decimal(brut)
    except InvalidOperation as erreur:
        raise ValidationError(f"« {champ} » doit être un nombre (lu : « {brut} »).") from erreur


def _entier(ligne: dict[str, str], champ: str, defaut: int = 0) -> int:
    brut = (ligne.get(champ) or "").strip()
    if not brut:
        return defaut
    try:
        return int(float(brut))
    except ValueError as erreur:
        raise ValidationError(f"« {champ} » doit être un nombre entier (lu : « {brut} »).") from erreur


def _booleen(ligne: dict[str, str], champ: str, defaut: bool = True) -> bool:
    brut = (ligne.get(champ) or "").strip().lower()
    if not brut:
        return defaut
    return brut in {"oui", "o", "1", "true", "vrai", "x"}


def _rattachement(modele, ligne: dict[str, str], champ: str, libelle: str):
    """L'objet nommé dans la colonne, ou None si elle est vide.

    Un nom renseigné mais introuvable reste une erreur, jamais un silence : une
    faute de frappe laisserait sinon l'étudiant sans rattachement, et rien ne
    le signalerait avant qu'on aille le chercher.
    """
    nom = (ligne.get(champ) or "").strip()
    if not nom:
        return None
    trouve = modele.objects.filter(nom__iexact=nom).first()
    if trouve is None:
        raise ValidationError(f"{libelle} : « {nom} ». Créez-le d'abord, ou laissez la colonne vide.")
    return trouve


def _slug_libre(modele, base: str, champ: str = "slug") -> str:
    """Un slug unique dérivé du titre, sans écraser un existant."""
    racine = slugify(base)[:180] or "entree"
    candidat, rang = racine, 2
    while modele.objects.filter(**{champ: candidat}).exists():
        candidat = f"{racine}-{rang}"
        rang += 1
    return candidat


# ══════════════════════════════════════════════
# Professeurs
# ══════════════════════════════════════════════

COLONNES_PROFESSEURS = [
    Colonne("nom", "Nom de famille", requise=True, exemple="Nisus"),
    Colonne("prenom", "Prénom", requise=True, exemple="Alain"),
    Colonne("specialite", "Spécialité principale", exemple="Théologie systématique"),
    Colonne("biographie", "Notice biographique", exemple="Docteur en théologie…"),
    Colonne("disciplines", "Disciplines, séparées par des virgules", exemple="Théologie, Exégèse"),
    Colonne("actif", "oui ou non", exemple="oui"),
]


def _importer_professeur(ligne: dict[str, str]) -> bool:
    nom = _exiger(ligne, "nom")
    prenom = _exiger(ligne, "prenom")

    # La clé naturelle est le couple nom/prénom : c'est ce que le secrétariat
    # recopie d'un fichier à l'autre, et il n'existe pas d'identifiant enseignant.
    professeur = Professeur.objects.filter(nom__iexact=nom, prenom__iexact=prenom).first()
    cree = professeur is None
    if cree:
        professeur = Professeur(nom=nom, prenom=prenom, slug=_slug_libre(Professeur, f"{prenom} {nom}"))

    professeur.specialite = ligne.get("specialite", "").strip()
    professeur.biographie = ligne.get("biographie", "").strip()
    professeur.actif = _booleen(ligne, "actif")
    professeur.save()

    noms_disciplines = [nom.strip() for nom in (ligne.get("disciplines") or "").split(",") if nom.strip()]
    if noms_disciplines:
        disciplines = []
        for nom_discipline in noms_disciplines:
            discipline = Discipline.objects.filter(nom__iexact=nom_discipline).first()
            if discipline is None:
                raise ValidationError(f"Discipline inconnue : « {nom_discipline} ». Créez-la d'abord.")
            disciplines.append(discipline)
        professeur.disciplines.set(disciplines)
    return cree


def _exporter_professeurs():
    for professeur in Professeur.objects.prefetch_related("disciplines").order_by("nom", "prenom"):
        yield [
            professeur.nom,
            professeur.prenom,
            professeur.specialite,
            professeur.biographie,
            ", ".join(discipline.nom for discipline in professeur.disciplines.all()),
            "oui" if professeur.actif else "non",
        ]


# ══════════════════════════════════════════════
# Étudiants
# ══════════════════════════════════════════════

COLONNES_ETUDIANTS = [
    # Sans exemple : la ligne d'exemple du gabarit montre la colonne vide, ce
    # qui est l'usage attendu. Y afficher « ETU2026001 » laissait croire qu'il
    # fallait inventer un numéro par ligne — exactement ce qu'on vient de lever.
    Colonne("numero_etudiant", "Laisser vide pour le faire attribuer — l'email sert alors de clé"),
    Colonne("nom", "Nom de famille", requise=True, exemple="Marceline"),
    Colonne("prenom", "Prénom", requise=True, exemple="Josiane"),
    Colonne("email", "Adresse électronique", requise=True, exemple="josiane.marceline@example.org"),
    Colonne("telephone", "Téléphone", exemple="+590 690 00 00 00"),
    Colonne("parcours", "Nom exact d'un parcours existant, ou vide", exemple="Licence en théologie"),
    Colonne("promotion", "Nom exact d'une promotion existante, ou vide", exemple="Promotion 2026"),
    Colonne("statut", "actif, inscrit, pre_inscrit, suspendu, diplome", exemple="actif"),
    Colonne("eglise", "Église d'appartenance", exemple="Église de Pointe-à-Pitre"),
]


def _importer_etudiant(ligne: dict[str, str]) -> bool:
    from django.utils import timezone

    from apps.accounts.models import User
    from apps.administration.services.admission import numero_etudiant_suivant

    nom = _exiger(ligne, "nom")
    prenom = _exiger(ligne, "prenom")
    # L'email est la clé de repli quand le fichier ne porte pas de numéro. Il
    # sert aussi à joindre l'étudiant pour qu'il définisse son mot de passe :
    # sans lui, le compte créé reste inatteignable.
    email = _exiger(ligne, "email")

    numero = (ligne.get("numero_etudiant") or "").strip()
    parcours = _rattachement(Parcours, ligne, "parcours", "Parcours inconnu")
    promotion = _rattachement(Promotion, ligne, "promotion", "Promotion inconnue")

    statut = (ligne.get("statut") or ProfilEtudiant.StatutInscription.PRE_INSCRIT).strip().lower()
    if statut not in ProfilEtudiant.StatutInscription.values:
        attendus = ", ".join(ProfilEtudiant.StatutInscription.values)
        raise ValidationError(f"Statut inconnu : « {statut} ». Valeurs attendues : {attendus}.")

    if numero:
        profil = ProfilEtudiant.objects.filter(numero_etudiant=numero).select_related("utilisateur").first()
    else:
        profil = ProfilEtudiant.objects.filter(utilisateur__email__iexact=email).select_related("utilisateur").first()
    cree = profil is None

    if cree:
        # Le compte est créé sans mot de passe utilisable : l'étudiant le
        # définit lui-même par le lien de réinitialisation. Un import ne doit
        # jamais fabriquer de mot de passe, ni le faire transiter.
        base = slugify(f"{prenom}.{nom}")[:140] or "etudiant"
        identifiant, rang = base, 2
        while User.objects.filter(username=identifiant).exists():
            identifiant = f"{base}{rang}"
            rang += 1
        compte = User.objects.create(
            username=identifiant,
            email=email,
            first_name=prenom,
            last_name=nom,
            phone=(ligne.get("telephone") or "").strip(),
            role=User.Role.ETUDIANT,
        )
        compte.set_unusable_password()
        compte.save(update_fields=["password"])
        # Un numéro absent du fichier est attribué ici par la même fonction que
        # l'acceptation d'une candidature : les deux voies alimentent la même
        # série, et aucune ne peut produire un numéro que l'autre a déjà donné.
        profil = ProfilEtudiant(
            utilisateur=compte,
            numero_etudiant=numero or numero_etudiant_suivant(timezone.now().year),
        )
    else:
        compte = profil.utilisateur
        compte.first_name = prenom
        compte.last_name = nom
        if ligne.get("email"):
            compte.email = ligne["email"].strip()
        if ligne.get("telephone"):
            compte.phone = ligne["telephone"].strip()
        compte.save(update_fields=["first_name", "last_name", "email", "phone"])

    # Une colonne laissée vide ne veut pas dire « efface » : un second dépôt,
    # partiel, ne doit pas détacher un étudiant déjà rattaché à son parcours.
    if parcours is not None:
        profil.parcours = parcours
    if promotion is not None:
        profil.promotion = promotion
    profil.statut_inscription = statut
    if ligne.get("eglise"):
        profil.eglise = ligne["eglise"].strip()
    profil.save()
    return cree


def _exporter_etudiants():
    requete = ProfilEtudiant.objects.select_related("utilisateur", "parcours", "promotion").order_by("numero_etudiant")
    for profil in requete:
        yield [
            profil.numero_etudiant,
            profil.utilisateur.last_name,
            profil.utilisateur.first_name,
            profil.utilisateur.email,
            profil.utilisateur.phone,
            profil.parcours.nom if profil.parcours_id else "",
            profil.promotion.nom if profil.promotion_id else "",
            profil.statut_inscription,
            getattr(profil, "eglise", "") or "",
        ]


# ══════════════════════════════════════════════
# Référentiel pédagogique — parcours et cours
# ══════════════════════════════════════════════

COLONNES_COURS = [
    Colonne("code", "Code du cours", exemple="THEO-101"),
    Colonne("titre", "Intitulé du cours", requise=True, exemple="Herméneutique biblique"),
    Colonne("discipline", "Nom exact de la discipline", requise=True, exemple="Théologie"),
    Colonne("ects", "Crédits ECTS", exemple="5"),
    Colonne("volume_horaire", "Heures", exemple="24"),
    Colonne("description", "Descriptif", exemple="Principes d'interprétation…"),
    Colonne("actif", "oui ou non", exemple="oui"),
]


def _importer_cours(ligne: dict[str, str]) -> bool:
    titre = _exiger(ligne, "titre")
    nom_discipline = _exiger(ligne, "discipline")
    discipline = Discipline.objects.filter(nom__iexact=nom_discipline).first()
    if discipline is None:
        raise ValidationError(f"Discipline inconnue : « {nom_discipline} ». Créez-la d'abord.")

    code = (ligne.get("code") or "").strip()
    # Le code fait clé quand il existe ; sinon le titre, qui reste ce que le
    # secrétariat manipule.
    cours = Cours.objects.filter(code=code).first() if code else Cours.objects.filter(titre__iexact=titre).first()
    cree = cours is None
    if cree:
        cours = Cours(titre=titre, slug=_slug_libre(Cours, titre))

    cours.titre = titre
    cours.discipline = discipline
    if code:
        cours.code = code
    cours.ects = _decimal(ligne, "ects", "0")
    cours.volume_horaire = _entier(ligne, "volume_horaire", 0)
    cours.description = ligne.get("description", "").strip()
    cours.actif = _booleen(ligne, "actif")
    cours.save()
    return cree


def _exporter_cours():
    for cours in Cours.objects.select_related("discipline").order_by("discipline__nom", "titre"):
        yield [
            cours.code,
            cours.titre,
            cours.discipline.nom if cours.discipline_id else "",
            cours.ects,
            cours.volume_horaire,
            cours.description,
            "oui" if cours.actif else "non",
        ]


# ══════════════════════════════════════════════
# Bibliothèque
# ══════════════════════════════════════════════

COLONNES_BIBLIOTHEQUE = [
    Colonne("titre", "Titre de l'ouvrage", requise=True, exemple="Théologie systématique"),
    Colonne("auteur", "Auteur", exemple="Louis Berkhof"),
    Colonne("editeur", "Éditeur", exemple="Excelsis"),
    Colonne("date_publication", "Année ou date", exemple="2010"),
    Colonne("isbn", "ISBN", exemple="9782755001234"),
    Colonne("cote", "Cote de rangement", exemple="TH-100"),
    Colonne("mots_cles", "Mots-clés séparés par des virgules", exemple="dogmatique, doctrine"),
    Colonne("discipline", "Nom exact de la discipline", exemple="Théologie"),
    Colonne("disponible", "oui ou non", exemple="oui"),
]


def _importer_notice(ligne: dict[str, str]) -> bool:
    titre = _exiger(ligne, "titre")
    isbn = (ligne.get("isbn") or "").strip()

    # L'ISBN est la clé quand il est fourni — c'est ce qui distingue deux
    # éditions du même titre. Sinon, titre et auteur ensemble.
    if isbn:
        notice = NoticeBibliographique.objects.filter(isbn=isbn).first()
    else:
        notice = NoticeBibliographique.objects.filter(
            titre__iexact=titre, auteur__iexact=(ligne.get("auteur") or "").strip()
        ).first()

    cree = notice is None
    if cree:
        notice = NoticeBibliographique(titre=titre)

    nom_discipline = (ligne.get("discipline") or "").strip()
    if nom_discipline:
        discipline = Discipline.objects.filter(nom__iexact=nom_discipline).first()
        if discipline is None:
            raise ValidationError(f"Discipline inconnue : « {nom_discipline} ». Créez-la d'abord.")
        notice.discipline = discipline

    notice.titre = titre
    notice.auteur = (ligne.get("auteur") or "").strip()
    notice.editeur = (ligne.get("editeur") or "").strip()
    notice.date_publication = (ligne.get("date_publication") or "").strip()
    notice.isbn = isbn
    notice.cote = (ligne.get("cote") or "").strip()
    notice.mots_cles = (ligne.get("mots_cles") or "").strip()
    notice.disponible = _booleen(ligne, "disponible")
    notice.save()
    return cree


def _exporter_notices():
    for notice in NoticeBibliographique.objects.select_related("discipline").order_by("titre"):
        yield [
            notice.titre,
            notice.auteur,
            notice.editeur,
            notice.date_publication,
            notice.isbn,
            notice.cote,
            notice.mots_cles,
            notice.discipline.nom if notice.discipline_id else "",
            "oui" if notice.disponible else "non",
        ]


# ══════════════════════════════════════════════
# Registre
# ══════════════════════════════════════════════

SCHEMAS: dict[str, Schema] = {
    schema.cle: schema
    for schema in (
        Schema(
            cle="professeurs",
            libelle="Corps enseignant",
            colonnes=COLONNES_PROFESSEURS,
            exporter=_exporter_professeurs,
            importer_ligne=_importer_professeur,
        ),
        Schema(
            cle="etudiants",
            libelle="Étudiants",
            colonnes=COLONNES_ETUDIANTS,
            exporter=_exporter_etudiants,
            importer_ligne=_importer_etudiant,
        ),
        Schema(
            cle="cours",
            libelle="Cours du référentiel",
            colonnes=COLONNES_COURS,
            exporter=_exporter_cours,
            importer_ligne=_importer_cours,
        ),
        Schema(
            cle="bibliotheque",
            libelle="Catalogue de la bibliothèque",
            colonnes=COLONNES_BIBLIOTHEQUE,
            exporter=_exporter_notices,
            importer_ligne=_importer_notice,
        ),
    )
}
