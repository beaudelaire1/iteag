"""
L'espace du personnel est pensé pour des utilisateurs qui n'ont pas grandi
avec le numérique, sans fermer la porte à ceux qui leur succéderont.

Ces cas verrouillent les garde-fous posés après l'audit du 25 septembre 2026 :
- aucune décision envoyant un courriel ne part sans avoir été choisie ;
- les compteurs de la liste des candidatures disent la vérité ;
- l'action groupée n'existe qu'en affichage compact ;
- les formulaires courants se remplissent avec l'essentiel ;
- inscrire un étudiant se fait en un seul écran.
"""

import re
from datetime import date

import pytest
from django.core import mail
from django.urls import reverse

from apps.academics.models import ProfilEtudiant, Promotion, SessionAcademique
from apps.accounts.models import User
from apps.administration.forms import AdminCoursForm, AdminSessionForm, PromotionForm
from apps.admissions.models import DossierCandidature
from apps.formations.models import Cours, Discipline, Parcours

pytestmark = pytest.mark.django_db

MOT_DE_PASSE = "MotDePasseSolide!2026"


@pytest.fixture
def secretaire(db):
    return User.objects.create_user(
        username="secretaire_confort",
        email="secretaire.confort@example.org",
        password=MOT_DE_PASSE,
        first_name="Viviane",
        role=User.Role.SECRETARIAT,
    )


@pytest.fixture
def parcours(db):
    return Parcours.objects.create(nom="ITEAG Pro", slug="iteag-pro-confort", type_parcours=Parcours.TypeParcours.PRO)


def _dossier(parcours, prenom, statut):
    return DossierCandidature.objects.create(
        nom="Candidat",
        prenom=prenom,
        email=f"{prenom.lower()}@example.org",
        parcours_souhaite=parcours,
        motivations="Servir.",
        statut=statut,
    )


# ──────────────────────────────────────────────
# Préférence d'affichage
# ──────────────────────────────────────────────


class TestPreferenceAffichage:
    def test_l_affichage_confortable_est_celui_de_tous_par_defaut(self, client, secretaire):
        client.force_login(secretaire)
        page = client.get(reverse("secretariat:dashboard")).content.decode()
        assert "affichage-confortable" in page
        assert "Passer en affichage compact" in page

    def test_basculer_revient_a_la_page_d_origine(self, client, secretaire):
        client.force_login(secretaire)
        origine = reverse("administration:candidatures")
        reponse = client.post(reverse("accounts:affichage"), {"affichage": "compact", "suivant": origine})
        assert reponse.status_code == 302
        assert reponse.url == origine
        secretaire.refresh_from_db()
        assert secretaire.affichage == User.Affichage.COMPACT
        page = client.get(origine).content.decode()
        assert "affichage-confortable" not in page
        assert "Passer en affichage confortable" in page

    def test_une_adresse_de_retour_exterieure_est_ignoree(self, client, secretaire):
        client.force_login(secretaire)
        reponse = client.post(
            reverse("accounts:affichage"), {"affichage": "compact", "suivant": "https://ailleurs.example/"}
        )
        assert "ailleurs.example" not in reponse.url

    def test_une_valeur_inconnue_ne_change_rien(self, client, secretaire):
        client.force_login(secretaire)
        client.post(reverse("accounts:affichage"), {"affichage": "geant"})
        secretaire.refresh_from_db()
        assert secretaire.affichage == User.Affichage.CONFORTABLE

    def test_le_volet_propose_aide_et_deconnexion(self, client, secretaire):
        client.force_login(secretaire)
        page = client.get(reverse("secretariat:dashboard")).content.decode()
        assert f'href="{reverse("accounts:aide")}"' in page
        assert f'action="{reverse("accounts:logout")}"' in page

    def test_la_page_d_aide_s_ouvre(self, client, secretaire):
        client.force_login(secretaire)
        page = client.get(reverse("accounts:aide")).content.decode()
        assert "Répondre à une candidature" in page

    def test_les_confirmations_restent_affichees_en_affichage_confortable(self, client, secretaire):
        client.force_login(secretaire)
        reponse = client.post(reverse("accounts:affichage"), {"affichage": "confortable"}, follow=True)
        # Le choix n'a pas changé : aucun message. On en provoque un.
        client.post(reverse("accounts:affichage"), {"affichage": "compact"})
        reponse = client.post(reverse("accounts:affichage"), {"affichage": "confortable"}, follow=True)
        assert 'data-flash="0"' in reponse.content.decode()


# ──────────────────────────────────────────────
# Candidatures
# ──────────────────────────────────────────────


class TestListeDesCandidatures:
    def test_les_compteurs_disent_le_nombre_reel(self, client, secretaire, parcours):
        _dossier(parcours, "Anne", DossierCandidature.Statut.SOUMIS)
        _dossier(parcours, "Bruno", DossierCandidature.Statut.SOUMIS)
        _dossier(parcours, "Chloe", DossierCandidature.Statut.REFUSE)
        client.force_login(secretaire)
        page = client.get(reverse("administration:candidatures")).content.decode()
        texte = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", page))
        assert "Toutes (3)" in texte
        assert "Soumis (2)" in texte
        assert "Refusé (1)" in texte
        assert "En examen (0)" in texte

    def test_l_action_groupee_n_existe_qu_en_affichage_compact(self, client, secretaire, parcours):
        _dossier(parcours, "Anne", DossierCandidature.Statut.SOUMIS)
        client.force_login(secretaire)
        confortable = client.get(reverse("administration:candidatures")).content.decode()
        assert 'name="bulk_statut"' not in confortable
        assert 'name="selected"' not in confortable

        secretaire.affichage = User.Affichage.COMPACT
        secretaire.save(update_fields=["affichage"])
        compact = client.get(reverse("administration:candidatures")).content.decode()
        assert 'name="bulk_statut"' in compact
        assert '<option value="">— Choisir un statut —</option>' in compact
        assert "data-confirmer=" in compact


class TestDecisionSurUneCandidature:
    def test_aucune_decision_n_est_choisie_d_avance(self, client, secretaire, parcours):
        dossier = _dossier(parcours, "Anne", DossierCandidature.Statut.EN_EXAMEN)
        client.force_login(secretaire)
        page = client.get(reverse("administration:candidature_detail", args=[dossier.pk])).content.decode()
        radios = re.findall(r'<input type="radio" name="statut"[^>]*>', page)
        assert len(radios) == 3
        assert not any("checked" in radio for radio in radios)
        assert all("required" in radio for radio in radios)

    def test_chaque_decision_qui_ecrit_au_candidat_demande_confirmation(self, client, secretaire, parcours):
        dossier = _dossier(parcours, "Anne", DossierCandidature.Statut.EN_EXAMEN)
        client.force_login(secretaire)
        page = client.get(reverse("administration:candidature_detail", args=[dossier.pk])).content.decode()
        for valeur in ("incomplet", "accepte", "refuse"):
            radio = re.search(rf'<input type="radio" name="statut" value="{valeur}"[^>]*>', page).group(0)
            assert "data-confirmer=" in radio, valeur

    def test_envoyer_la_fiche_sans_choix_ne_change_rien(self, client, secretaire, parcours):
        dossier = _dossier(parcours, "Anne", DossierCandidature.Statut.EN_EXAMEN)
        client.force_login(secretaire)
        client.post(reverse("administration:candidature_detail", args=[dossier.pk]), {"commentaire": "Vu."})
        dossier.refresh_from_db()
        assert dossier.statut == DossierCandidature.Statut.EN_EXAMEN
        assert mail.outbox == []


# ──────────────────────────────────────────────
# Inscrire un étudiant en un seul écran
# ──────────────────────────────────────────────


class TestInscriptionEnUnEcran:
    def test_cree_le_compte_le_dossier_et_le_numero(
        self, client, secretaire, parcours, django_capture_on_commit_callbacks
    ):
        client.force_login(secretaire)
        with django_capture_on_commit_callbacks(execute=True):
            reponse = client.post(
                reverse("administration:etudiant_create"),
                {
                    "prenom": "Marthe",
                    "nom": "Lebon",
                    "email": "marthe.lebon@example.org",
                    "parcours": parcours.pk,
                    "envoyer_invitation": "on",
                    "statut_inscription": ProfilEtudiant.StatutInscription.INSCRIT,
                },
            )
        assert reponse.status_code == 302
        profil = ProfilEtudiant.objects.get(utilisateur__email="marthe.lebon@example.org")
        assert profil.numero_etudiant.startswith("ETU")
        assert profil.parcours == parcours
        assert profil.utilisateur.role == User.Role.ETUDIANT
        assert not profil.utilisateur.has_usable_password()
        assert [message.to for message in mail.outbox] == [["marthe.lebon@example.org"]]

    def test_sans_invitation_aucun_courriel(self, client, secretaire, django_capture_on_commit_callbacks):
        client.force_login(secretaire)
        with django_capture_on_commit_callbacks(execute=True):
            client.post(
                reverse("administration:etudiant_create"),
                {
                    "prenom": "Paul",
                    "nom": "Ancien",
                    "email": "paul.ancien@example.org",
                    "statut_inscription": ProfilEtudiant.StatutInscription.DIPLOME,
                },
            )
        assert ProfilEtudiant.objects.filter(utilisateur__email="paul.ancien@example.org").exists()
        assert mail.outbox == []

    def test_une_adresse_deja_inscrite_est_refusee(self, client, secretaire):
        compte = User.objects.create_user(username="deja", email="deja@example.org", role=User.Role.ETUDIANT)
        ProfilEtudiant.objects.create(utilisateur=compte, numero_etudiant="ETU2026999")
        client.force_login(secretaire)
        reponse = client.post(
            reverse("administration:etudiant_create"),
            {
                "prenom": "Autre",
                "nom": "Personne",
                "email": "DEJA@example.org",
                "statut_inscription": ProfilEtudiant.StatutInscription.INSCRIT,
            },
        )
        assert reponse.status_code == 200
        assert "ETU2026999" in reponse.content.decode()
        assert ProfilEtudiant.objects.count() == 1


# ──────────────────────────────────────────────
# Formulaires allégés
# ──────────────────────────────────────────────


class TestFormulairesAlleges:
    def test_un_cours_se_cree_avec_titre_et_discipline(self):
        discipline = Discipline.objects.create(nom="Homilétique", slug="homiletique-d")
        Cours.objects.create(titre="Homilétique", slug="homiletique", discipline=discipline)
        formulaire = AdminCoursForm(data={"titre": "Homilétique", "discipline": discipline.pk, "ects": "2.5"})
        assert formulaire.is_valid(), formulaire.errors
        cours = formulaire.save()
        # Un second cours du même titre reçoit une adresse distincte au lieu
        # d'une erreur sur un champ que personne n'a rempli.
        assert cours.slug == "homiletique-2"

    def test_les_reglages_rares_sont_ranges_sous_plus_d_options(self):
        formulaire = AdminCoursForm()
        visibles = [champ.name for champ in formulaire.champs_principaux()]
        assert visibles[:3] == ["titre", "discipline", "parcours"]
        assert "slug" not in visibles
        assert {champ.name for champ in formulaire.champs_optionnels()} == {"code", "ects", "actif", "slug"}

    def test_une_session_deduit_son_nom_et_son_annee(self):
        formulaire = AdminSessionForm(
            data={
                "periode": SessionAcademique.Periode.PAQUES,
                "date_debut": "2027-04-12",
                "date_fin": "2027-04-16",
                "statut": SessionAcademique.StatutSession.PLANIFIEE,
            }
        )
        assert formulaire.is_valid(), formulaire.errors
        session = formulaire.save()
        assert session.nom == "Session de Pâques 2027"
        assert session.annee_academique == "2026-2027"
        assert session.date_debut == date(2027, 4, 12)

    def test_une_promotion_deduit_son_nom(self, parcours):
        formulaire = PromotionForm(
            data={"parcours": parcours.pk, "annee_debut": 2026, "annee_fin": 2029, "actif": "on"}
        )
        assert formulaire.is_valid(), formulaire.errors
        assert formulaire.save().nom == "Promotion 2026-2029 — ITEAG Pro"

    def test_les_listes_ne_montrent_plus_de_tirets(self):
        formulaire = AdminCoursForm()
        assert formulaire.fields["discipline"].empty_label == "— Choisir —"

    def test_une_promotion_du_meme_nom_est_signalee(self, parcours):
        Promotion.objects.create(
            nom="Promotion 2026-2029 — ITEAG Pro", parcours=parcours, annee_debut=2026, annee_fin=2029
        )
        formulaire = PromotionForm(data={"parcours": parcours.pk, "annee_debut": 2026, "annee_fin": 2029})
        assert not formulaire.is_valid()
        assert "nom" in formulaire.errors
