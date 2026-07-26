"""
Test de fumée des routes à paramètre : fiches, formulaires d'édition,
confirmations de suppression.

Les routes sans paramètre sont couvertes ailleurs. Celles-ci sont plus
exposées : elles chargent un objet, en dérivent un contexte, et le rendent. Une
relation renommée, un champ retiré ou un `get_absolute_url` cassé s'y traduit
par une erreur 500 que rien d'autre ne détecte — ces pages ne sont atteintes
qu'en cliquant.

Un jeu de données minimal mais complet est monté une fois, puis chaque route
est appelée avec le rôle qui a le droit de la voir. Le contrat vérifié est le
même que pour les listes : **aucune erreur serveur**, jamais.
"""

import pytest
from django.urls import reverse

from apps.academics.models import (
    VAE,
    CoursDeSession,
    CreditECTS,
    DemandeInscriptionCours,
    Paiement,
    ProfilEtudiant,
    Promotion,
    SessionAcademique,
    Stage,
)
from apps.accounts.models import User
from apps.admissions.models import DossierCandidature
from apps.documents.models import DocumentAdministratif
from apps.elearning.models import Chapitre, Lecon, ModuleFormation, VideoAsset
from apps.formations.models import Cours, Discipline, Parcours, Professeur, Tarif
from apps.library.models import NoticeBibliographique
from apps.lms.models import Evaluation


@pytest.fixture
def univers(db):
    """
    Un exemplaire de chaque objet que les fiches savent afficher.

    Monté d'un bloc plutôt qu'en fixtures séparées : ces routes se lisent comme
    un parcours — un module contient un chapitre qui contient une leçon — et le
    jeu perdrait son sens éclaté en morceaux.
    """
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
    for role in (User.Role.ADMIN, User.Role.SECRETARIAT, User.Role.ENSEIGNANT, User.Role.ETUDIANT):
        monde[role] = User.objects.create_user(
            username=f"detail_{role}",
            email=f"detail_{role}@iteag.org",
            password="motdepasse-long-12",
            first_name="Test",
            last_name=role.capitalize(),
            role=role,
        )

    monde["professeur"] = Professeur.objects.create(
        user=monde[User.Role.ENSEIGNANT], nom="Sainval", prenom="Joseph", slug="joseph-sainval"
    )
    monde["promotion"] = Promotion.objects.create(
        nom="Promotion détail", parcours=monde["parcours"], annee_debut=2026, annee_fin=2032
    )
    monde["profil"] = ProfilEtudiant.objects.create(
        utilisateur=monde[User.Role.ETUDIANT],
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
    monde["demande"] = DemandeInscriptionCours.objects.create(
        etudiant=monde["profil"], cours_session=monde["cours_session"]
    )
    monde["evaluation"] = Evaluation.objects.create(
        etudiant=monde["profil"],
        cours_session=monde["cours_session"],
        statut=Evaluation.StatutEvaluation.SOUMIS,
    )

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
        etudiant=monde[User.Role.ETUDIANT],
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
        uploade_par=monde[User.Role.ENSEIGNANT],
    )
    monde["lecon"] = Lecon.objects.create(
        chapitre=monde["chapitre"],
        titre="Leçon introductive",
        slug="lecon-introductive",
        ordre=1,
        type_lecon=Lecon.TypeLecon.VIDEO,
        video=monde["video"],
    )

    # ── Divers ──
    monde["candidature"] = DossierCandidature.objects.create(
        nom="Céleste",
        prenom="Marc",
        email="marc.celeste@example.org",
        parcours_souhaite=monde["parcours"],
    )
    monde["notice"] = NoticeBibliographique.objects.create(titre="Institution chrétienne", auteur="Jean Calvin")

    return monde


def cas_de_test(monde) -> list[tuple[str, str, dict]]:
    """(rôle, nom de route, paramètres) — le rôle est celui qui a le droit de voir."""
    admin, secretariat = User.Role.ADMIN, User.Role.SECRETARIAT
    enseignant, etudiant = User.Role.ENSEIGNANT, User.Role.ETUDIANT

    return [
        # ── Portail administratif ──
        (secretariat, "administration:candidature_detail", {"pk": monde["candidature"].pk}),
        (secretariat, "administration:enrollment_request_detail", {"pk": monde["demande"].pk}),
        (secretariat, "administration:course_offering_update", {"pk": monde["cours_session"].pk}),
        (secretariat, "administration:etudiant_update", {"pk": monde["profil"].pk}),
        (secretariat, "administration:payment_update", {"pk": monde["paiement"].pk}),
        (secretariat, "administration:promotion_update", {"pk": monde["promotion"].pk}),
        (secretariat, "administration:credit_ects_update", {"pk": monde["credit"].pk}),
        (secretariat, "administration:stage_update", {"pk": monde["stage"].pk}),
        (secretariat, "administration:session_update", {"pk": monde["session"].pk}),
        (admin, "administration:course_update", {"pk": monde["cours"].pk}),
        (admin, "administration:professeur_update", {"pk": monde["professeur"].pk}),
        (admin, "administration:user_update", {"pk": monde[etudiant].pk}),
        (admin, "administration:tarif_update", {"pk": monde["tarif"].pk}),
        (admin, "administration:vae_update", {"pk": monde["vae"].pk}),
        # Confirmations de suppression : ce sont des pages, pas des actions.
        (admin, "administration:course_delete", {"pk": monde["cours"].pk}),
        (admin, "administration:course_offering_delete", {"pk": monde["cours_session"].pk}),
        (admin, "administration:etudiant_delete", {"pk": monde["profil"].pk}),
        (admin, "administration:payment_delete", {"pk": monde["paiement"].pk}),
        (admin, "administration:professeur_delete", {"pk": monde["professeur"].pk}),
        (admin, "administration:promotion_delete", {"pk": monde["promotion"].pk}),
        (admin, "administration:credit_ects_delete", {"pk": monde["credit"].pk}),
        (admin, "administration:stage_delete", {"pk": monde["stage"].pk}),
        (admin, "administration:vae_delete", {"pk": monde["vae"].pk}),
        (admin, "administration:tarif_delete", {"pk": monde["tarif"].pk}),
        (admin, "administration:session_delete", {"pk": monde["session"].pk}),
        (admin, "administration:user_delete", {"pk": monde[etudiant].pk}),
        # ── Portail enseignant ──
        (enseignant, "elearning:enseignant_structure", {"slug": monde["module"].slug}),
        (enseignant, "elearning:enseignant_module_modifier", {"slug": monde["module"].slug}),
        (enseignant, "elearning:enseignant_audience", {"slug": monde["module"].slug}),
        (enseignant, "elearning:enseignant_lecon_creer", {"chapitre_pk": monde["chapitre"].pk}),
        (enseignant, "elearning:enseignant_lecon_modifier", {"pk": monde["lecon"].pk}),
        (enseignant, "elearning:enseignant_lecon_supprimer", {"pk": monde["lecon"].pk}),
        (enseignant, "elearning:enseignant_chapitre_supprimer", {"pk": monde["chapitre"].pk}),
        (enseignant, "elearning:enseignant_soustitre", {"video_pk": monde["video"].pk}),
        (enseignant, "lms:course_detail", {"pk": monde["cours_session"].pk}),
        (enseignant, "lms:grade_evaluation", {"pk": monde["evaluation"].pk}),
        (enseignant, "lms:resource_upload", {"cours_pk": monde["cours_session"].pk}),
        (enseignant, "lms:announcement_create", {"cours_pk": monde["cours_session"].pk}),
        # ── Espace étudiant ──
        (etudiant, "etudiant:course_offering_detail", {"pk": monde["cours_session"].pk}),
        (etudiant, "etudiant:enrollment_request_create", {"pk": monde["cours_session"].pk}),
        (etudiant, "etudiant:submit_evaluation", {"pk": monde["evaluation"].pk}),
        # ── Pages publiques ──
        ("", "elearning:module_detail", {"slug": monde["module"].slug}),
        ("", "formations:cours_detail", {"slug": monde["cours"].slug}),
        ("", "formations:parcours_detail", {"slug": monde["parcours"].slug}),
        ("", "formations:professeur_detail", {"slug": monde["professeur"].slug}),
        ("", "library:notice_detail", {"pk": monde["notice"].pk}),
        ("", "elearning:verifier_attestation", {"code": "code-inexistant"}),
    ]


@pytest.mark.django_db
def test_le_jeu_de_cas_couvre_bien_les_fiches(univers):
    """
    Garde-fou du garde-fou.

    Un test de fumée dont la liste se serait vidée passerait sans rien
    vérifier, et rassurerait à tort. On ancre donc le nombre de fiches
    couvertes : le faire baisser demande un geste délibéré.
    """
    cas = cas_de_test(univers)
    assert len(cas) >= 45, f"Seules {len(cas)} fiches sont couvertes"
    assert len({nom for _, nom, _ in cas}) == len(cas), "Une route est listée deux fois"


@pytest.mark.django_db
def test_aucune_fiche_ne_provoque_d_erreur_serveur(client, univers):
    """
    Chaque fiche est appelée avec le rôle qui a le droit de la voir.

    L'assertion porte sur l'absence de 500 et non sur un code précis : une
    redirection ou un refus restent des réponses correctes selon l'état de
    l'objet. Ce qui n'est jamais correct, c'est que le serveur tombe.
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
def test_les_fiches_du_personnel_sont_fermees_aux_etudiants(client, univers):
    """
    Une fiche n'est pas moins sensible qu'une liste.

    Un contrôle posé sur la liste et oublié sur le détail est l'erreur
    classique : l'étudiant ne voit pas le lien, mais l'adresse reste devinable.
    """
    client.force_login(univers[User.Role.ETUDIANT])
    fuites = []

    for _role, nom_route, parametres in cas_de_test(univers):
        if not nom_route.startswith(("administration:", "secretariat:")):
            continue
        if client.get(reverse(nom_route, kwargs=parametres)).status_code == 200:
            fuites.append(nom_route)

    assert not fuites, f"Fiches du personnel accessibles à un étudiant : {fuites}"


@pytest.mark.django_db
def test_un_enseignant_n_atteint_pas_le_contenu_d_un_confrere(client, univers):
    """La restriction de propriété doit tenir aussi sur les fiches."""
    autre = User.objects.create_user(
        username="autre_prof_detail",
        email="autre_prof_detail@iteag.org",
        password="motdepasse-long-12",
        role=User.Role.ENSEIGNANT,
    )
    Professeur.objects.create(user=autre, nom="Intrus", prenom="Paul", slug="paul-intrus")
    client.force_login(autre)

    for nom_route, parametres in [
        ("elearning:enseignant_structure", {"slug": univers["module"].slug}),
        ("elearning:enseignant_module_modifier", {"slug": univers["module"].slug}),
        ("elearning:enseignant_lecon_modifier", {"pk": univers["lecon"].pk}),
        ("lms:course_detail", {"pk": univers["cours_session"].pk}),
        ("lms:grade_evaluation", {"pk": univers["evaluation"].pk}),
    ]:
        reponse = client.get(reverse(nom_route, kwargs=parametres))
        assert reponse.status_code != 200, f"{nom_route} accessible à un enseignant tiers"
