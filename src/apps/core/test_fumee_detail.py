"""
Test de fumée des routes à paramètre : fiches, formulaires, actions.

Les routes sans paramètre sont couvertes ailleurs. Celles-ci sont plus
exposées : elles chargent un objet, en dérivent un contexte, et le rendent. Une
relation renommée, un champ retiré ou un `get_absolute_url` cassé s'y traduit
par une erreur 500 que rien d'autre ne détecte — ces pages ne sont atteintes
qu'en cliquant. C'est aussi là que se logent les défauts de cloisonnement : le
contrôle posé sur la liste et oublié sur le détail est l'erreur classique.

Le garde-fou tient à `FABRIQUES` : **toute** route à paramètre du projet doit
y figurer, faute de quoi le premier test de ce fichier échoue en la nommant.
Une nouvelle vue de détail ne peut donc plus échapper au contrôle par simple
oubli — il faut un geste délibéré pour l'exclure, et l'exclusion se justifie
sur place.

Trois propriétés sont vérifiées :

1. **aucune erreur serveur**, avec le rôle qui a le droit de voir la page ;
2. **une page privée refuse l'anonyme** — la déclaration d'un rôle vaut
   déclaration de page privée ;
3. **un tiers du même rôle n'atteint pas le contenu d'un autre** — c'est ce que
   le seul contrôle de rôle laisse passer.
"""

import uuid
from datetime import time, timedelta
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import get_resolver, reverse
from django.utils import timezone
from wagtail.models import Page

from apps.academics.models import (
    VAE,
    CoursDeSession,
    CreditECTS,
    DemandeInscriptionCours,
    Paiement,
    ProfilEtudiant,
    Promotion,
    PropositionEnseignement,
    SessionAcademique,
    Stage,
)
from apps.academics.models_assiduite import SeanceCours
from apps.accounts.models import User
from apps.admissions.models import DossierCandidature, PieceDemandee
from apps.commerce.models import Commande, DestinationLivraison, ProduitLivre, TarifLivraison, TypeLivraison
from apps.core.models import AbonneNewsletter
from apps.core.services.notifications import notifier
from apps.documents.models import DocumentAdministratif, DocumentRedige
from apps.elearning.models import (
    AttestationModule,
    Chapitre,
    InscriptionModule,
    Lecon,
    ModuleFormation,
    RessourceLecon,
    VideoAsset,
)
from apps.formations.models import Cours, Discipline, Parcours, Professeur, Tarif
from apps.library.models import Emprunt, NoticeBibliographique, SuspensionBibliotheque
from apps.lms.models import (
    Annonce,
    Choix,
    Devoir,
    Evaluation,
    GroupeEtudiants,
    Question,
    RessourcePedagogique,
)
from apps.paiements.models import Reglement
from apps.website.models import NewsIndexPage, NewsPage
from apps.website.models_publications import Article, ImageArticle, TemoignageEtudiant

ADMIN, SECRETARIAT = User.Role.ADMIN, User.Role.SECRETARIAT
ENSEIGNANT, ETUDIANT = User.Role.ENSEIGNANT, User.Role.ETUDIANT
PUBLIC = ""

# Préfixes de routes appartenant à un espace réservé au personnel.
PREFIXES_PERSONNEL = ("administration:", "secretariat:", "redaction:")

# Routes internes, hors périmètre applicatif.
PREFIXES_INTERNES = ("wagtail", "admin:", "django")


# ──────────────────────────────────────────────
# Le monde minimal
# ──────────────────────────────────────────────


@pytest.fixture
def univers(db, settings, tmp_path):
    """
    Un exemplaire de chaque objet que les routes savent charger.

    Monté d'un bloc plutôt qu'en fixtures séparées : ces routes se lisent comme
    un parcours — un module contient un chapitre qui contient une leçon — et le
    jeu perdrait son sens éclaté en morceaux.
    """
    # Les fichiers déposés atterrissent dans un répertoire jetable : certains
    # modèles lisent la taille du fichier à l'enregistrement, ce qui suppose
    # qu'il existe vraiment.
    settings.MEDIA_ROOT = tmp_path

    # Attention : `User.Role.ETUDIANT` vaut « etudiant ». Le profil est donc
    # rangé sous « profil » pour ne pas écraser le compte du même nom.
    monde = {}

    monde["parcours"] = Parcours.objects.create(
        nom="Diplômant", slug="diplomant-detail", type_parcours=Parcours.TypeParcours.DIPLOMANT_ITEAG
    )
    monde["discipline"] = Discipline.objects.create(nom="Théologie systématique", slug="theo-syst-detail")
    monde["cours"] = Cours.objects.create(
        titre="Doctrine de la révélation", slug="doctrine-revelation", discipline=monde["discipline"]
    )

    # ── Comptes ──
    for role in (ADMIN, SECRETARIAT, ENSEIGNANT, ETUDIANT):
        monde[role] = User.objects.create_user(
            username=f"detail_{role}",
            email=f"detail_{role}@iteag.org",
            password="motdepasse-long-12",
            first_name="Test",
            last_name=role.capitalize(),
            role=role,
        )

    monde["professeur"] = Professeur.objects.create(
        user=monde[ENSEIGNANT], nom="Sainval", prenom="Joseph", slug="joseph-sainval"
    )
    monde["promotion"] = Promotion.objects.create(
        nom="Promotion détail", parcours=monde["parcours"], annee_debut=2026, annee_fin=2032
    )
    monde["profil"] = ProfilEtudiant.objects.create(
        utilisateur=monde[ETUDIANT],
        parcours=monde["parcours"],
        promotion=monde["promotion"],
        numero_etudiant="ETU-DETAIL-1",
        statut_inscription=ProfilEtudiant.StatutInscription.ACTIF,
    )

    # ── Session et offre de cours ──
    monde["session"] = SessionAcademique.objects.create(
        nom="Session de détail",
        periode=SessionAcademique.Periode.JUILLET,
        annee_academique="2026-2027",
        date_debut="2027-07-05",
        date_fin="2027-07-10",
    )
    monde["cours_session"] = CoursDeSession.objects.create(
        session=monde["session"], cours=monde["cours"], enseignant=monde["professeur"]
    )
    monde["seance_assiduite"] = SeanceCours.objects.create(
        cours_session=monde["cours_session"],
        date="2027-07-05",
        heure_debut=time(9, 0),
        heure_fin=time(12, 0),
        cree_par=monde[ADMIN],
    )
    monde["demande"] = DemandeInscriptionCours.objects.create(
        etudiant=monde["profil"], cours_session=monde["cours_session"]
    )
    monde["proposition"] = PropositionEnseignement.objects.create(
        cours_session=monde["cours_session"], professeur=monde["professeur"]
    )
    monde["evaluation"] = Evaluation.objects.create(
        etudiant=monde["profil"],
        cours_session=monde["cours_session"],
        statut=Evaluation.StatutEvaluation.SOUMIS,
    )

    # ── Travail demandé ──
    monde["devoir"] = Devoir.objects.create(
        cours_session=monde["cours_session"],
        titre="Contrôle de lecture",
        modalite=Devoir.Modalite.QCM,
        date_ouverture=timezone.now() - timedelta(days=1),
        date_fermeture=timezone.now() + timedelta(days=7),
    )
    monde["question"] = Question.objects.create(devoir=monde["devoir"], enonce="Qui écrit ?", points=Decimal("2"))
    monde["choix"] = Choix.objects.create(question=monde["question"], libelle="Paul", correct=True)
    monde["copie"] = Evaluation.objects.create(
        etudiant=monde["profil"], cours_session=monde["cours_session"], devoir=monde["devoir"]
    )
    monde["annonce"] = Annonce.objects.create(
        cours_session=monde["cours_session"],
        auteur=monde[ENSEIGNANT],
        titre="Salle changée",
        contenu="Nous serons en B12.",
    )
    monde["ressource_cours"] = RessourcePedagogique.objects.create(
        cours_session=monde["cours_session"],
        titre="Plan du cours",
        fichier=SimpleUploadedFile("plan.pdf", b"%PDF-1.4 plan"),
        uploade_par=monde[ENSEIGNANT],
    )
    monde["groupe"] = GroupeEtudiants.objects.create(cours_session=monde["cours_session"], nom="Équipe 1")

    # ── Dossier académique ──
    monde["paiement"] = Paiement.objects.create(
        etudiant=monde["profil"],
        session=monde["session"],
        montant="180.00",
        mode=Paiement.ModePaiement.VIREMENT,
        date_paiement="2027-06-01",
    )
    monde["credit"] = CreditECTS.objects.create(
        etudiant=monde["profil"],
        cours=monde["cours"],
        session=monde["session"],
        ects_obtenus="2.5",
        source=CreditECTS.SourceCredit.ITEAG,
        date_validation="2027-07-10",
    )
    monde["stage"] = Stage.objects.create(
        etudiant=monde["profil"],
        type_stage="Stage pastoral",
        lieu="Église du Lamentin",
        date_debut="2027-01-05",
        date_fin="2027-03-05",
        ects="30",
    )
    monde["vae"] = VAE.objects.create(
        etudiant=monde["profil"], description_experience="Dix ans de ministère.", ects_demandes="20"
    )
    monde["tarif"] = Tarif.objects.create(
        formule=Tarif.FormuleTarif.TOUTES_SESSIONS, type_membre=Tarif.TypeMembre.AUTRE, montant_session="180.00"
    )
    # `DocumentAdministratif.etudiant` pointe le compte, pas le profil.
    monde["document"] = DocumentAdministratif.objects.create(
        etudiant=monde[ETUDIANT],
        type_document=DocumentAdministratif.TypeDocument.ATTESTATION,
    )

    # ── Formation vidéo ──
    monde["module"] = ModuleFormation.objects.create(
        titre="Module détail",
        slug="module-detail",
        discipline=monde["discipline"],
        responsable=monde["professeur"],
        politique_acces=ModuleFormation.PolitiqueAcces.PUBLIC,
        statut=ModuleFormation.StatutPublication.PUBLIE,
    )
    monde["chapitre"] = Chapitre.objects.create(module=monde["module"], titre="Chapitre premier", ordre=1)
    monde["video"] = VideoAsset.objects.create(
        titre="Séance introductive",
        cle_stockage="videos/detail.mp4",
        fournisseur="local",
        statut_traitement=VideoAsset.StatutTraitement.PRET,
        uploade_par=monde[ENSEIGNANT],
    )
    monde["lecon"] = Lecon.objects.create(
        chapitre=monde["chapitre"],
        titre="Leçon introductive",
        slug="lecon-introductive",
        ordre=1,
        type_lecon=Lecon.TypeLecon.VIDEO,
        video=monde["video"],
    )
    monde["ressource_lecon"] = RessourceLecon.objects.create(
        lecon=monde["lecon"], titre="Notes de séance", fichier=SimpleUploadedFile("notes.pdf", b"%PDF-1.4 notes")
    )
    monde["inscription_module"] = InscriptionModule.objects.create(
        etudiant=monde["profil"], module=monde["module"], statut=InscriptionModule.StatutAcces.ACTIF
    )
    monde["attestation"] = AttestationModule.objects.create(inscription=monde["inscription_module"])

    # Un second module, celui-là fermé : le contenu d'un module public est
    # lisible par construction, et une leçon publique ne prouve rien du
    # cloisonnement. Les routes de lecture pointent donc celui-ci, dont notre
    # étudiant a l'accès et dont personne d'autre ne l'a.
    monde["module_prive"] = ModuleFormation.objects.create(
        titre="Module réservé",
        slug="module-reserve",
        discipline=monde["discipline"],
        responsable=monde["professeur"],
        politique_acces=ModuleFormation.PolitiqueAcces.SUR_OCTROI,
        statut=ModuleFormation.StatutPublication.PUBLIE,
    )
    monde["chapitre_prive"] = Chapitre.objects.create(module=monde["module_prive"], titre="Chapitre réservé", ordre=1)
    monde["lecon_privee"] = Lecon.objects.create(
        chapitre=monde["chapitre_prive"],
        titre="Leçon réservée",
        slug="lecon-reservee",
        ordre=1,
        type_lecon=Lecon.TypeLecon.VIDEO,
        video=monde["video"],
    )
    monde["ressource_privee"] = RessourceLecon.objects.create(
        lecon=monde["lecon_privee"],
        titre="Notes réservées",
        fichier=SimpleUploadedFile("reservees.pdf", b"%PDF-1.4 reservees"),
    )
    InscriptionModule.objects.create(
        etudiant=monde["profil"], module=monde["module_prive"], statut=InscriptionModule.StatutAcces.ACTIF
    )

    # ── Candidatures ──
    monde["candidature"] = DossierCandidature.objects.create(
        nom="Céleste",
        prenom="Marc",
        email="marc.celeste@example.org",
        parcours_souhaite=monde["parcours"],
    )
    monde["piece"] = PieceDemandee.objects.create(dossier=monde["candidature"], libelle="Acte de naissance")

    # ── Bibliothèque ──
    monde["notice"] = NoticeBibliographique.objects.create(titre="Institution chrétienne", auteur="Jean Calvin")
    monde["emprunt"] = Emprunt.objects.create(
        notice=monde["notice"],
        emprunteur=monde[ETUDIANT],
        date_retour_prevue=timezone.localdate() + timedelta(days=21),
    )
    monde["suspension"] = SuspensionBibliotheque.objects.create(
        emprunteur=monde[ETUDIANT],
        emprunt=monde["emprunt"],
        jours_retard=3,
        jours_suspension=3,
        date_debut=timezone.localdate(),
        date_fin=timezone.localdate() + timedelta(days=2),
    )
    monde["produit"] = ProduitLivre.objects.create(
        titre="Institution chrétienne",
        slug="institution-chretienne",
        sku="LIV-001",
        prix_ttc=Decimal("35.00"),
        stock_physique=3,
    )
    # Les tarifs de référence sont posés par une migration : on en ajoute un
    # dont le poids ne peut heurter aucun d'eux plutôt que d'en supposer un.
    monde["tarif_livraison"] = TarifLivraison.objects.create(
        destination=DestinationLivraison.GUADELOUPE,
        type_livraison=TypeLivraison.STANDARD,
        poids_max_grammes=999_999,
        prix_ttc=Decimal("6.50"),
    )
    monde["commande"] = Commande.objects.create(
        numero="CMD-DETAIL-1",
        prenom="Marc",
        nom="Céleste",
        email="marc.celeste@example.org",
        adresse="1 rue du Temple",
        code_postal="97110",
        ville="Pointe-à-Pitre",
    )

    # ── Paiement en ligne ──
    monde["reglement"] = Reglement.objects.create(
        nature=Reglement.Nature.FRAIS_INSCRIPTION,
        utilisateur=monde[ETUDIANT],
        etudiant=monde["profil"],
        email=monde[ETUDIANT].email,
        libelle="Frais d'inscription",
        montant_ttc=Decimal("50.00"),
    )

    # ── Publications ──
    monde["article"] = Article.objects.create(
        titre="La révélation chez Calvin",
        slug="revelation-calvin",
        auteur=monde["professeur"],
        corps="<p>Un texte.</p>",
        statut=Article.Statut.PUBLIE,
        date_publication=timezone.now(),
    )
    monde["illustration"] = ImageArticle.objects.create(
        article=monde["article"], fichier=SimpleUploadedFile("figure.png", b"figure"), legende="Figure 1"
    )
    monde["temoignage"] = TemoignageEtudiant.objects.create(
        nom_affiche="Maya Jean",
        promotion="Promotion détail",
        texte="<p>Un témoignage public de contrôle.</p>",
        consentement_publication=True,
        statut=TemoignageEtudiant.Statut.PUBLIE,
        valide_le=timezone.now(),
        valide_par=monde[ADMIN],
    )

    # Une actualité vit dans l'arbre Wagtail : elle a besoin de son index, qui
    # a besoin de la racine créée par les migrations. « add_child » ne vérifie
    # pas « parent_page_types » — cette contrainte n'existe qu'à l'écran de
    # création —, l'index est donc accroché directement à la racine.
    racine = Page.objects.filter(depth=1).first()
    index_actualites = NewsIndexPage(title="Actualités", slug="actualites-detail")
    racine.add_child(instance=index_actualites)
    monde["actualite"] = NewsPage(
        title="Rentrée académique",
        slug="rentree-academique-detail",
        date=timezone.localdate(),
        body="<p>La rentrée est fixée.</p>",
    )
    index_actualites.add_child(instance=monde["actualite"])

    monde["document_administratif"] = DocumentAdministratif.objects.create(
        etudiant=monde[ETUDIANT],
        type_document=DocumentAdministratif.TypeDocument.ATTESTATION,
    )
    monde["document_redige"] = DocumentRedige.objects.create(
        titre="Convocation du conseil",
        genre=DocumentRedige.Genre.CONVOCATION,
        objet="Séance du conseil pédagogique",
        corps=[("paragraphe", "<p>Vous êtes convoqué.</p>")],
        redige_par=monde[SECRETARIAT],
    )

    # ── Divers ──
    monde["notification"] = notifier(monde[ETUDIANT], "Une nouvelle note", envoyer_par_email=False)
    monde["abonne"] = AbonneNewsletter.objects.create(email="abonne.detail@example.org")

    return monde


# ──────────────────────────────────────────────
# Les fabriques
# ──────────────────────────────────────────────
#
# `nom de route: (rôle autorisé, arguments d'URL)`. Le rôle est celui qui a le
# droit de voir la page ; « PUBLIC » désigne une page ouverte, et vaut
# déclaration que l'anonyme y est le bienvenu.

FABRIQUES = {
    # ── Comptes ──
    "accounts:password_reset_confirm": (PUBLIC, lambda m: {"uidb64": "MQ", "token": "jeton-perime"}),
    # ── Portail administratif — candidatures ──
    "administration:candidature_detail": (SECRETARIAT, lambda m: {"pk": m["candidature"].pk}),
    "administration:demander_pieces": (SECRETARIAT, lambda m: {"pk": m["candidature"].pk}),
    "administration:piece_decision": (SECRETARIAT, lambda m: {"pk": m["piece"].pk}),
    "administration:piece_fichier": (SECRETARIAT, lambda m: {"pk": m["piece"].pk}),
    # ── Portail administratif — scolarité ──
    "administration:course_offering_update": (SECRETARIAT, lambda m: {"pk": m["cours_session"].pk}),
    "administration:course_offering_delete": (ADMIN, lambda m: {"pk": m["cours_session"].pk}),
    "administration:emargement_pdf": (SECRETARIAT, lambda m: {"pk": m["cours_session"].pk}),
    "administration:cours_session_presences": (SECRETARIAT, lambda m: {"pk": m["cours_session"].pk}),
    "administration:session_pv_deliberation_pdf": (SECRETARIAT, lambda m: {"pk": m["session"].pk}),
    "administration:assiduite_cours": (ENSEIGNANT, lambda m: {"pk": m["cours_session"].pk}),
    "administration:assiduite_feuille": (ENSEIGNANT, lambda m: {"pk": m["seance_assiduite"].pk}),
    "administration:enrollment_request_detail": (SECRETARIAT, lambda m: {"pk": m["demande"].pk}),
    "administration:enrollment_request_action": (SECRETARIAT, lambda m: {"pk": m["demande"].pk}),
    "administration:enrollment_proof_download": (SECRETARIAT, lambda m: {"pk": m["demande"].pk}),
    "administration:etudiant_detail": (SECRETARIAT, lambda m: {"pk": m["profil"].pk}),
    "administration:etudiant_update": (SECRETARIAT, lambda m: {"pk": m["profil"].pk}),
    "administration:etudiant_delete": (ADMIN, lambda m: {"pk": m["profil"].pk}),
    "administration:payment_update": (SECRETARIAT, lambda m: {"pk": m["paiement"].pk}),
    "administration:payment_delete": (ADMIN, lambda m: {"pk": m["paiement"].pk}),
    "administration:promotion_update": (SECRETARIAT, lambda m: {"pk": m["promotion"].pk}),
    "administration:promotion_delete": (ADMIN, lambda m: {"pk": m["promotion"].pk}),
    "administration:credit_ects_update": (SECRETARIAT, lambda m: {"pk": m["credit"].pk}),
    "administration:credit_ects_delete": (ADMIN, lambda m: {"pk": m["credit"].pk}),
    "administration:stage_update": (SECRETARIAT, lambda m: {"pk": m["stage"].pk}),
    "administration:stage_delete": (ADMIN, lambda m: {"pk": m["stage"].pk}),
    "administration:vae_update": (ADMIN, lambda m: {"pk": m["vae"].pk}),
    "administration:vae_delete": (ADMIN, lambda m: {"pk": m["vae"].pk}),
    "administration:session_update": (SECRETARIAT, lambda m: {"pk": m["session"].pk}),
    "administration:session_delete": (ADMIN, lambda m: {"pk": m["session"].pk}),
    # ── Portail administratif — référentiel ──
    "administration:course_update": (ADMIN, lambda m: {"pk": m["cours"].pk}),
    "administration:course_delete": (ADMIN, lambda m: {"pk": m["cours"].pk}),
    "administration:discipline_update": (SECRETARIAT, lambda m: {"pk": m["discipline"].pk}),
    "administration:discipline_delete": (SECRETARIAT, lambda m: {"pk": m["discipline"].pk}),
    "administration:parcours_update": (SECRETARIAT, lambda m: {"pk": m["parcours"].pk}),
    "administration:parcours_delete": (SECRETARIAT, lambda m: {"pk": m["parcours"].pk}),
    "administration:professeur_detail": (SECRETARIAT, lambda m: {"pk": m["professeur"].pk}),
    "administration:professeur_update": (ADMIN, lambda m: {"pk": m["professeur"].pk}),
    "administration:professeur_delete": (ADMIN, lambda m: {"pk": m["professeur"].pk}),
    "administration:professeur_associer_module": (ADMIN, lambda m: {"pk": m["professeur"].pk}),
    "administration:professeur_proposer_cours": (ADMIN, lambda m: {"pk": m["professeur"].pk}),
    "administration:tarif_update": (ADMIN, lambda m: {"pk": m["tarif"].pk}),
    "administration:tarif_delete": (ADMIN, lambda m: {"pk": m["tarif"].pk}),
    "administration:user_update": (ADMIN, lambda m: {"pk": m[ETUDIANT].pk}),
    "administration:user_delete": (ADMIN, lambda m: {"pk": m[ETUDIANT].pk}),
    # ── Portail administratif — tableurs ──
    "administration:tableur_detail": (SECRETARIAT, lambda m: {"cle": "etudiants"}),
    "administration:tableur_export": (SECRETARIAT, lambda m: {"cle": "etudiants", "format_fichier": "csv"}),
    "administration:tableur_gabarit": (SECRETARIAT, lambda m: {"cle": "etudiants", "format_fichier": "csv"}),
    "administration:tableur_import": (SECRETARIAT, lambda m: {"cle": "etudiants"}),
    # ── Candidature, côté candidat ──
    "admissions:candidature_confirmation": (PUBLIC, lambda m: {"token": m["candidature"].token_suivi}),
    "admissions:candidature_suivi": (PUBLIC, lambda m: {"token": m["candidature"].token_suivi}),
    "admissions:deposer_piece": (
        PUBLIC,
        lambda m: {"token": m["candidature"].token_suivi, "piece_id": m["piece"].pk},
    ),
    # ── Redirections d'anciennes adresses ──
    "ancienne_url_elearning": (PUBLIC, lambda m: {"chemin": "catalogue/"}),
    "ancienne_url_enseignant": (PUBLIC, lambda m: {"chemin": "cours/"}),
    # ── Boutique ──
    "commerce:produit_detail": (PUBLIC, lambda m: {"slug": m["produit"].slug}),
    "commerce:panier_ajouter": (PUBLIC, lambda m: {"pk": m["produit"].pk}),
    "commerce:panier_modifier": (PUBLIC, lambda m: {"pk": m["produit"].pk}),
    "commerce:panier_retirer": (PUBLIC, lambda m: {"pk": m["produit"].pk}),
    "commerce:commande_suivi": (PUBLIC, lambda m: {"jeton": m["commande"].jeton_suivi}),
    "commerce:commande_action": (SECRETARIAT, lambda m: {"pk": m["commande"].pk}),
    "commerce:produit_modifier": (SECRETARIAT, lambda m: {"pk": m["produit"].pk}),
    "commerce:stock_ajuster": (SECRETARIAT, lambda m: {"pk": m["produit"].pk}),
    "commerce:tarif_livraison_modifier": (SECRETARIAT, lambda m: {"pk": m["tarif_livraison"].pk}),
    "commerce:tarif_livraison_supprimer": (SECRETARIAT, lambda m: {"pk": m["tarif_livraison"].pk}),
    # ── Socle ──
    "core:newsletter_confirmation": (PUBLIC, lambda m: {"token": m["abonne"].token_confirmation}),
    "core:newsletter_desinscription": (PUBLIC, lambda m: {"token": m["abonne"].token_desinscription}),
    "core:notification_lue": (ETUDIANT, lambda m: {"pk": m["notification"].pk}),
    "core:notification_supprimer": (ETUDIANT, lambda m: {"pk": m["notification"].pk}),
    # ── Documents ──
    "documents:delete": (ETUDIANT, lambda m: {"pk": m["document"].pk}),
    "documents:download": (ETUDIANT, lambda m: {"pk": m["document"].pk}),
    "documents:generate": (
        ETUDIANT,
        lambda m: {"document_type": DocumentAdministratif.TypeDocument.ATTESTATION},
    ),
    # ── Formation vidéo — côté public et étudiant ──
    "elearning:module_detail": (PUBLIC, lambda m: {"slug": m["module"].slug}),
    "elearning:verifier_attestation": (PUBLIC, lambda m: {"code": m["attestation"].code_verification}),
    "elearning:module_demander_acces": (ETUDIANT, lambda m: {"slug": m["module"].slug}),
    # Sur le module fermé : le contenu d'un module public ne prouverait rien.
    "elearning:lecon_detail": (
        ETUDIANT,
        lambda m: {"slug": m["module_prive"].slug, "lecon_slug": m["lecon_privee"].slug},
    ),
    "elearning:lecon_playback": (
        ETUDIANT,
        lambda m: {"slug": m["module_prive"].slug, "lecon_slug": m["lecon_privee"].slug},
    ),
    "elearning:lecon_metadata": (
        ETUDIANT,
        lambda m: {"slug": m["module_prive"].slug, "lecon_slug": m["lecon_privee"].slug},
    ),
    "elearning:lecon_progression": (
        ETUDIANT,
        lambda m: {"slug": m["module_prive"].slug, "lecon_slug": m["lecon_privee"].slug},
    ),
    "elearning:ressource_telecharger": (
        ETUDIANT,
        lambda m: {
            "slug": m["module_prive"].slug,
            "lecon_slug": m["lecon_privee"].slug,
            "pk": m["ressource_privee"].pk,
        },
    ),
    "elearning:attestation_telecharger": (ETUDIANT, lambda m: {"pk": m["attestation"].pk}),
    "elearning:fichier_video": (ETUDIANT, lambda m: {"jeton": "jeton-non-signe"}),
    # ── Formation vidéo — côté enseignant ──
    "elearning:enseignant_structure": (ENSEIGNANT, lambda m: {"slug": m["module"].slug}),
    "elearning:enseignant_module_modifier": (ENSEIGNANT, lambda m: {"slug": m["module"].slug}),
    "elearning:enseignant_audience": (ENSEIGNANT, lambda m: {"slug": m["module"].slug}),
    "elearning:enseignant_publier": (ENSEIGNANT, lambda m: {"slug": m["module"].slug}),
    "elearning:enseignant_depublier": (ENSEIGNANT, lambda m: {"slug": m["module"].slug}),
    "elearning:enseignant_chapitre_creer": (ENSEIGNANT, lambda m: {"slug": m["module"].slug}),
    "elearning:enseignant_chapitre_supprimer": (ENSEIGNANT, lambda m: {"pk": m["chapitre"].pk}),
    "elearning:enseignant_lecon_creer": (ENSEIGNANT, lambda m: {"chapitre_pk": m["chapitre"].pk}),
    "elearning:enseignant_lecons_ordonner": (ENSEIGNANT, lambda m: {"chapitre_pk": m["chapitre"].pk}),
    "elearning:enseignant_lecon_modifier": (ENSEIGNANT, lambda m: {"pk": m["lecon"].pk}),
    "elearning:enseignant_lecon_supprimer": (ENSEIGNANT, lambda m: {"pk": m["lecon"].pk}),
    "elearning:enseignant_ressource_creer": (ENSEIGNANT, lambda m: {"lecon_pk": m["lecon"].pk}),
    "elearning:enseignant_ressource_supprimer": (ENSEIGNANT, lambda m: {"pk": m["ressource_lecon"].pk}),
    "elearning:enseignant_soustitre": (ENSEIGNANT, lambda m: {"video_pk": m["video"].pk}),
    "elearning:enseignant_video_modifier": (ENSEIGNANT, lambda m: {"pk": m["video"].pk}),
    "elearning:enseignant_video_supprimer": (ENSEIGNANT, lambda m: {"pk": m["video"].pk}),
    # ── Portail enseignant ──
    "enseignant:proposition_reponse": (ENSEIGNANT, lambda m: {"pk": m["proposition"].pk}),
    # ── Espace étudiant ──
    "etudiant:course_offering_detail": (ETUDIANT, lambda m: {"pk": m["cours_session"].pk}),
    "etudiant:enrollment_request_create": (ETUDIANT, lambda m: {"pk": m["cours_session"].pk}),
    "etudiant:enrollment_request_cancel": (ETUDIANT, lambda m: {"pk": m["demande"].pk}),
    "etudiant:submit_evaluation": (ETUDIANT, lambda m: {"pk": m["evaluation"].pk}),
    "etudiant:questionnaire": (ETUDIANT, lambda m: {"pk": m["copie"].pk}),
    # ── Pages publiques de l'institut ──
    "formations:cours_detail": (PUBLIC, lambda m: {"slug": m["cours"].slug}),
    "formations:parcours_detail": (PUBLIC, lambda m: {"slug": m["parcours"].slug}),
    "formations:professeur_detail": (PUBLIC, lambda m: {"slug": m["professeur"].slug}),
    # ── Bibliothèque ──
    "library:emprunt_action": (SECRETARIAT, lambda m: {"pk": m["emprunt"].pk}),
    "library:emprunt_annuler": (ETUDIANT, lambda m: {"pk": m["emprunt"].pk}),
    "library:emprunt_modifier": (SECRETARIAT, lambda m: {"pk": m["emprunt"].pk}),
    "library:emprunt_supprimer": (SECRETARIAT, lambda m: {"pk": m["emprunt"].pk}),
    "library:suspension_lever": (SECRETARIAT, lambda m: {"pk": m["suspension"].pk}),
    "library:notice_annuler": (ETUDIANT, lambda m: {"pk": m["notice"].pk}),
    "library:notice_detail": (PUBLIC, lambda m: {"pk": m["notice"].pk}),
    "library:notice_disponibilite": (SECRETARIAT, lambda m: {"pk": m["notice"].pk}),
    "library:notice_modifier": (SECRETARIAT, lambda m: {"pk": m["notice"].pk}),
    "library:notice_reserver": (ETUDIANT, lambda m: {"pk": m["notice"].pk}),
    "library:notice_supprimer": (SECRETARIAT, lambda m: {"pk": m["notice"].pk}),
    # ── Salle de cours ──
    "lms:course_detail": (ENSEIGNANT, lambda m: {"pk": m["cours_session"].pk}),
    "lms:prepare_evaluations": (ENSEIGNANT, lambda m: {"pk": m["cours_session"].pk}),
    "lms:parametres_evaluation": (ENSEIGNANT, lambda m: {"pk": m["cours_session"].pk}),
    "lms:publish_grades": (ENSEIGNANT, lambda m: {"pk": m["cours_session"].pk}),
    "lms:grade_evaluation": (ENSEIGNANT, lambda m: {"pk": m["evaluation"].pk}),
    "lms:publish_grade": (ENSEIGNANT, lambda m: {"pk": m["evaluation"].pk}),
    "lms:revise_grade": (ENSEIGNANT, lambda m: {"pk": m["evaluation"].pk}),
    "lms:accorder_delai": (ENSEIGNANT, lambda m: {"pk": m["evaluation"].pk}),
    "lms:evaluation_fichier": (ENSEIGNANT, lambda m: {"pk": m["evaluation"].pk, "genre": "soumis"}),
    "lms:resource_upload": (ENSEIGNANT, lambda m: {"cours_pk": m["cours_session"].pk}),
    "lms:resource_update": (ENSEIGNANT, lambda m: {"pk": m["ressource_cours"].pk}),
    "lms:resource_delete": (ENSEIGNANT, lambda m: {"pk": m["ressource_cours"].pk}),
    "lms:announcement_create": (ENSEIGNANT, lambda m: {"cours_pk": m["cours_session"].pk}),
    "lms:announcement_update": (ENSEIGNANT, lambda m: {"pk": m["annonce"].pk}),
    "lms:announcement_delete": (ENSEIGNANT, lambda m: {"pk": m["annonce"].pk}),
    "lms:devoir_create_pour_cours": (ENSEIGNANT, lambda m: {"cours_pk": m["cours_session"].pk}),
    "lms:devoir_detail": (ENSEIGNANT, lambda m: {"pk": m["devoir"].pk}),
    "lms:devoir_update": (ENSEIGNANT, lambda m: {"pk": m["devoir"].pk}),
    "lms:devoir_action": (ENSEIGNANT, lambda m: {"pk": m["devoir"].pk}),
    "lms:basculer_depot": (ENSEIGNANT, lambda m: {"pk": m["copie"].pk}),
    "lms:questionnaire": (ENSEIGNANT, lambda m: {"pk": m["devoir"].pk}),
    "lms:questionnaire_recorriger": (ENSEIGNANT, lambda m: {"pk": m["devoir"].pk}),
    "lms:question_create": (ENSEIGNANT, lambda m: {"pk": m["devoir"].pk}),
    "lms:question_detail": (ENSEIGNANT, lambda m: {"pk": m["question"].pk}),
    "lms:question_update": (ENSEIGNANT, lambda m: {"pk": m["question"].pk}),
    "lms:question_delete": (ENSEIGNANT, lambda m: {"pk": m["question"].pk}),
    "lms:choix_create": (ENSEIGNANT, lambda m: {"pk": m["question"].pk}),
    "lms:choix_delete": (ENSEIGNANT, lambda m: {"pk": m["choix"].pk}),
    "lms:groupe_update": (ENSEIGNANT, lambda m: {"pk": m["groupe"].pk}),
    "lms:groupe_delete": (ENSEIGNANT, lambda m: {"pk": m["groupe"].pk}),
    "lms:groupe_message": (ENSEIGNANT, lambda m: {"pk": m["groupe"].pk}),
    # ── Paiement en ligne ──
    "paiements:acheter_module": (ETUDIANT, lambda m: {"slug": m["module"].slug}),
    "paiements:checkout": (ETUDIANT, lambda m: {"pk": m["reglement"].pk}),
    "paiements:session_checkout": (ETUDIANT, lambda m: {"pk": m["reglement"].pk}),
    "paiements:succes": (ETUDIANT, lambda m: {"pk": m["reglement"].pk}),
    "paiements:annulation": (ETUDIANT, lambda m: {"pk": m["reglement"].pk}),
    "paiements:recu": (ETUDIANT, lambda m: {"pk": m["reglement"].pk}),
    "paiements:payer_commande": (PUBLIC, lambda m: {"jeton": m["commande"].jeton_suivi}),
    "paiements:payer_inscription": (ETUDIANT, lambda m: {"pk": m["demande"].pk}),
    # ── Articles de recherche ──
    "website:article_detail": (PUBLIC, lambda m: {"slug": m["article"].slug}),
    "website:article_edition": (ENSEIGNANT, lambda m: {"pk": m["article"].pk}),
    "website:article_soumettre": (ENSEIGNANT, lambda m: {"pk": m["article"].pk}),
    "website:article_demande_retrait": (ENSEIGNANT, lambda m: {"pk": m["article"].pk}),
    "website:article_supprimer": (ENSEIGNANT, lambda m: {"pk": m["article"].pk}),
    "website:article_illustration": (ENSEIGNANT, lambda m: {"pk": m["article"].pk}),
    "website:illustration_supprimer": (ENSEIGNANT, lambda m: {"pk": m["illustration"].pk}),
    # La relecture revient à la direction seule : l'article paraît sous la
    # signature d'un enseignant et sous le nom de l'institut.
    "website:article_decision": (ADMIN, lambda m: {"pk": m["article"].pk}),
    # ── Actualités ──
    "website:actualite_edition": (SECRETARIAT, lambda m: {"pk": m["actualite"].pk}),
    "website:actualite_decision": (SECRETARIAT, lambda m: {"pk": m["actualite"].pk}),
    "website:temoignage_public": (PUBLIC, lambda m: {"pk": m["temoignage"].pk}),
    # ── Documents rédigés ──
    "redaction:document_edition": (SECRETARIAT, lambda m: {"pk": m["document_redige"].pk}),
    "redaction:document_decision": (SECRETARIAT, lambda m: {"pk": m["document_redige"].pk}),
    "redaction:document_pdf": (SECRETARIAT, lambda m: {"pk": m["document_redige"].pk}),
    "redaction:document_etat_pdf": (SECRETARIAT, lambda m: {"pk": m["document_redige"].pk}),
    "documents:status": (ETUDIANT, lambda m: {"pk": m["document_administratif"].pk}),
}

# Routes dont la propriété n'est pas contrôlable par un tiers du même rôle, et
# pourquoi. Toute entrée doit se justifier : sans cela, la liste absorberait le
# premier cas gênant et le garde-fou perdrait son sens.
PROPRIETE_NON_APPLICABLE = {
    # Le catalogue de session est commun : tout étudiant voit l'offre et peut
    # demander à s'y inscrire. Il n'y a pas de propriétaire à protéger.
    "etudiant:course_offering_detail",
    "etudiant:enrollment_request_create",
    # Le module est en accès public dans ce jeu de données : c'est ce qui est
    # testé, et sa page de vente s'adresse à qui n'y a pas encore accès.
    "elearning:module_demander_acces",
    "paiements:acheter_module",
    # Le type de document est un choix, pas un objet : chaque étudiant génère
    # le sien. Le cloisonnement porte sur « documents:download ».
    "documents:generate",
}


def routes_a_parametre() -> set[str]:
    """Noms de toutes les routes du projet qui attendent au moins un paramètre."""
    noms = set()

    def parcourir(resolver, prefixe=""):
        for motif in resolver.url_patterns:
            if hasattr(motif, "url_patterns"):
                parcourir(motif, prefixe + (motif.namespace + ":" if motif.namespace else ""))
            elif motif.name and motif.pattern.regex.groups > 0:
                nom = prefixe + motif.name
                if not nom.startswith(PREFIXES_INTERNES):
                    noms.add(nom)

    parcourir(get_resolver())
    return noms


def cas_de_test(monde) -> list[tuple[str, str, dict]]:
    """(rôle, nom de route, paramètres) — le rôle est celui qui a le droit de voir."""
    return [(role, nom, fabrique(monde)) for nom, (role, fabrique) in sorted(FABRIQUES.items())]


# ──────────────────────────────────────────────
# Le garde-fou du garde-fou
# ──────────────────────────────────────────────


def test_toute_route_a_parametre_possede_une_fabrique():
    """
    Une vue de détail ne doit pas pouvoir naître hors du contrôle.

    C'est la pièce maîtresse de ce fichier : sans elle, la liste vieillit en
    silence et le test rassure à tort. Ajouter une route à paramètre oblige
    désormais à dire qui a le droit de la voir — la question même que les
    défauts de cloisonnement laissent sans réponse.
    """
    manquantes = sorted(routes_a_parametre() - set(FABRIQUES))
    assert not manquantes, (
        "Fabrique manquante pour :\n  "
        + "\n  ".join(manquantes)
        + "\n\nDéclarez-les dans FABRIQUES (apps/core/test_fumee_detail.py) : "
        "le rôle qui a le droit de voir la page, et les arguments d'URL."
    )


def test_aucune_fabrique_ne_survit_a_sa_route():
    """Une fabrique orpheline désigne une route renommée ou retirée."""
    orphelines = sorted(set(FABRIQUES) - routes_a_parametre())
    assert not orphelines, f"Fabriques sans route correspondante : {orphelines}"


@pytest.mark.django_db
def test_les_fabriques_produisent_des_adresses_valides(univers):
    """Un jeu de données incomplet ferait passer les tests suivants pour rien."""
    for _role, nom_route, parametres in cas_de_test(univers):
        assert reverse(nom_route, kwargs=parametres)


# ──────────────────────────────────────────────
# Les trois propriétés
# ──────────────────────────────────────────────


@pytest.mark.django_db
def test_aucune_route_ne_provoque_d_erreur_serveur(client, univers):
    """
    Chaque route est appelée avec le rôle qui a le droit de la voir.

    L'assertion porte sur l'absence de 500 et non sur un code précis : une
    redirection, un refus ou un « méthode non autorisée » restent des réponses
    correctes selon l'état de l'objet. Ce qui n'est jamais correct, c'est que
    le serveur tombe.
    """
    defaillantes = []

    for role, nom_route, parametres in cas_de_test(univers):
        client.logout()
        if role:
            client.force_login(univers[role])
        reponse = client.get(reverse(nom_route, kwargs=parametres))
        if reponse.status_code >= 500:
            defaillantes.append(f"{nom_route} ({role or 'anonyme'}) → {reponse.status_code}")

    assert not defaillantes, "Routes en erreur serveur :\n" + "\n".join(defaillantes)


@pytest.mark.django_db
def test_les_routes_privees_refusent_l_anonyme(client, univers):
    """
    Déclarer un rôle, c'est déclarer une page privée.

    Un visiteur sans compte doit être renvoyé vers la connexion ou éconduit ;
    il ne doit en aucun cas obtenir la page.
    """
    ouvertes = []

    for role, nom_route, parametres in cas_de_test(univers):
        if not role:
            continue
        client.logout()
        if client.get(reverse(nom_route, kwargs=parametres)).status_code == 200:
            ouvertes.append(nom_route)

    assert not ouvertes, f"Routes privées servies à un anonyme : {ouvertes}"


@pytest.mark.django_db
def test_les_routes_du_personnel_sont_fermees_aux_etudiants(client, univers):
    """
    Une fiche n'est pas moins sensible qu'une liste.

    Un contrôle posé sur la liste et oublié sur le détail est l'erreur
    classique : l'étudiant ne voit pas le lien, mais l'adresse reste devinable.
    """
    client.force_login(univers[ETUDIANT])
    fuites = []

    for _role, nom_route, parametres in cas_de_test(univers):
        if not nom_route.startswith(PREFIXES_PERSONNEL):
            continue
        if client.get(reverse(nom_route, kwargs=parametres)).status_code == 200:
            fuites.append(nom_route)

    assert not fuites, f"Routes du personnel accessibles à un étudiant : {fuites}"


@pytest.mark.django_db
def test_un_tiers_du_meme_role_n_atteint_pas_le_bien_d_un_autre(client, univers):
    """
    Le contrôle de rôle ne suffit pas : il faut celui de la propriété.

    C'est exactement la faille qu'une page servie « à tout compte connecté »
    ouvre — l'enseignant d'à côté lit la copie, l'étudiant d'à côté lit le
    règlement. Les deux intrus ont le bon rôle et ne possèdent rien.
    """
    intrus = {
        ENSEIGNANT: User.objects.create_user(
            username="intrus_prof",
            email="intrus_prof@iteag.org",
            password="motdepasse-long-12",
            role=ENSEIGNANT,
        ),
        ETUDIANT: User.objects.create_user(
            username="intrus_etu",
            email="intrus_etu@iteag.org",
            password="motdepasse-long-12",
            role=ETUDIANT,
        ),
    }
    Professeur.objects.create(user=intrus[ENSEIGNANT], nom="Intrus", prenom="Paul", slug="paul-intrus")
    autre_parcours = Parcours.objects.create(
        nom="Autre parcours", slug="autre-parcours-intrus", type_parcours=Parcours.TypeParcours.LIBRE
    )
    ProfilEtudiant.objects.create(
        utilisateur=intrus[ETUDIANT],
        parcours=autre_parcours,
        promotion=Promotion.objects.create(
            nom="Promotion intruse", parcours=autre_parcours, annee_debut=2026, annee_fin=2032
        ),
        numero_etudiant="ETU-INTRUS-1",
        statut_inscription=ProfilEtudiant.StatutInscription.ACTIF,
    )

    fuites = []
    for role, nom_route, parametres in cas_de_test(univers):
        if role not in intrus or nom_route in PROPRIETE_NON_APPLICABLE:
            continue
        client.logout()
        client.force_login(intrus[role])
        if client.get(reverse(nom_route, kwargs=parametres)).status_code == 200:
            fuites.append(f"{nom_route} ({role})")

    assert not fuites, "Contenu d'autrui servi à un tiers du même rôle :\n" + "\n".join(fuites)


@pytest.mark.django_db
def test_le_reglement_d_un_autre_reste_fermé(client, univers):
    """
    Le cas qui a motivé l'extension de ce fichier.

    Les pages de retour de paiement chargeaient le règlement par son seul
    identifiant. Le test est écrit à part pour qu'il nomme le défaut plutôt que
    de se fondre dans une liste.
    """
    curieux = User.objects.create_user(
        username="curieux_paiement",
        email="curieux_paiement@iteag.org",
        password="motdepasse-long-12",
        role=ETUDIANT,
    )
    client.force_login(curieux)

    for nom_route in ("paiements:succes", "paiements:annulation", "paiements:recu"):
        reponse = client.get(reverse(nom_route, kwargs={"pk": univers["reglement"].pk}))
        assert reponse.status_code == 404, f"{nom_route} → {reponse.status_code}"


@pytest.mark.django_db
def test_une_adresse_inexistante_ne_fait_pas_tomber_le_serveur(client, univers):
    """Un identifiant périmé — signet, lien recopié — se solde par un 404, pas par un 500."""
    client.force_login(univers[SECRETARIAT])
    for nom_route, parametres in (
        ("administration:candidature_detail", {"pk": 999_999}),
        ("administration:etudiant_detail", {"pk": 999_999}),
        ("library:notice_detail", {"pk": 999_999}),
        ("paiements:succes", {"pk": uuid.uuid4()}),
        ("commerce:commande_suivi", {"jeton": uuid.uuid4()}),
        ("formations:cours_detail", {"slug": "cours-disparu"}),
    ):
        reponse = client.get(reverse(nom_route, kwargs=parametres))
        assert reponse.status_code < 500, f"{nom_route} → {reponse.status_code}"


@pytest.mark.django_db
def test_le_jeu_de_cas_couvre_bien_les_routes(univers):
    """
    Un test de fumée dont la liste se serait vidée passerait sans rien
    vérifier, et rassurerait à tort. On ancre donc le nombre de routes
    couvertes : le faire baisser demande un geste délibéré.
    """
    cas = cas_de_test(univers)
    assert len(cas) >= 140, f"Seules {len(cas)} routes sont couvertes"
    assert len({nom for _, nom, _ in cas}) == len(cas), "Une route est listée deux fois"


@pytest.mark.django_db
def test_l_etudiant_du_monde_lit_bien_le_module_qui_lui_est_ouvert(univers, client):
    """
    Contre-épreuve du test de propriété.

    Si la leçon réservée était fermée à tout le monde, le contrôle de
    cloisonnement passerait sans rien démontrer. On vérifie donc que celui qui
    y a droit l'obtient réellement.
    """
    client.force_login(univers[ETUDIANT])
    reponse = client.get(
        reverse(
            "elearning:lecon_detail",
            kwargs={"slug": univers["module_prive"].slug, "lecon_slug": univers["lecon_privee"].slug},
        )
    )
    assert reponse.status_code == 200
