"""Tests du pilotage des accès à la formation vidéo, côté administration."""

import pytest
from django.urls import reverse

from apps.academics.models import ProfilEtudiant, Promotion
from apps.accounts.models import User
from apps.core.models import JournalAudit
from apps.elearning.models import InscriptionModule, JournalAccesVideo, ModuleFormation
from apps.elearning.services.octroi import octroyer
from apps.formations.models import Parcours


@pytest.fixture
def secretaire(db):
    return User.objects.create_user(
        username="sec_video",
        email="sec_video@iteag.org",
        password="motdepasse-long-12",
        role=User.Role.SECRETARIAT,
    )


@pytest.fixture
def parcours(db):
    return Parcours.objects.create(
        nom="Diplômant", slug="diplomant-video", type_parcours=Parcours.TypeParcours.DIPLOMANT_ITEAG
    )


@pytest.fixture
def promotion(db, parcours):
    return Promotion.objects.create(nom="Promotion 2025", parcours=parcours, annee_debut=2025, annee_fin=2031)


@pytest.fixture
def etudiants(db, parcours, promotion):
    profils = []
    for rang in range(3):
        utilisateur = User.objects.create_user(
            username=f"etu{rang}",
            email=f"etu{rang}@iteag.org",
            password="motdepasse-long-12",
            first_name=f"Prénom{rang}",
            last_name=f"Nom{rang}",
            role=User.Role.ETUDIANT,
        )
        profils.append(
            ProfilEtudiant.objects.create(
                utilisateur=utilisateur,
                parcours=parcours,
                promotion=promotion,
                numero_etudiant=f"ETU-2025-{rang:03d}",
                statut_inscription=ProfilEtudiant.StatutInscription.ACTIF,
            )
        )
    return profils


@pytest.fixture
def module_publie(db):
    return ModuleFormation.objects.create(
        titre="Théologie pratique",
        slug="theologie-pratique",
        statut=ModuleFormation.StatutPublication.PUBLIE,
    )


@pytest.fixture
def lecon(db, module_publie):
    """Une leçon minimale, pour rattacher des entrées de journal."""
    from apps.elearning.models import Chapitre, Lecon, VideoAsset

    chapitre = Chapitre.objects.create(module=module_publie, titre="Chapitre 1", ordre=1)
    video = VideoAsset.objects.create(
        titre="Séance",
        cle_stockage="videos/pilotage.mp4",
        duree_secondes=300,
        statut_traitement=VideoAsset.StatutTraitement.PRET,
    )
    return Lecon.objects.create(
        chapitre=chapitre, titre="Séance", slug="seance", video=video, ordre=1, duree_secondes=300
    )


@pytest.mark.django_db
class TestVueDesAcces:
    def test_le_secretariat_accede_a_la_liste(self, client, secretaire):
        client.force_login(secretaire)
        assert client.get(reverse("administration:acces")).status_code == 200

    def test_un_etudiant_est_refuse(self, client, etudiants):
        client.force_login(etudiants[0].utilisateur)
        assert client.get(reverse("administration:acces")).status_code in (302, 403)

    def test_filtre_par_module(self, client, secretaire, etudiants, module_publie, db):
        autre = ModuleFormation.objects.create(titre="Autre module", slug="autre-module")
        octroyer(etudiants[0], module_publie, notifier_etudiant=False)
        octroyer(etudiants[1], autre, notifier_etudiant=False)

        client.force_login(secretaire)
        reponse = client.get(reverse("administration:acces"), {"module": module_publie.slug})
        assert len(reponse.context["acces"]) == 1

    def test_recherche_par_nom(self, client, secretaire, etudiants, module_publie):
        for profil in etudiants:
            octroyer(profil, module_publie, notifier_etudiant=False)
        client.force_login(secretaire)
        reponse = client.get(reverse("administration:acces"), {"q": "Nom1"})
        assert len(reponse.context["acces"]) == 1


@pytest.mark.django_db
class TestActionsDeMasse:
    def _acces(self, etudiants, module):
        return [octroyer(profil, module, notifier_etudiant=False) for profil in etudiants]

    def test_suspension_groupee(self, client, secretaire, etudiants, module_publie):
        acces = self._acces(etudiants, module_publie)
        client.force_login(secretaire)
        client.post(
            reverse("administration:acces_action"),
            {"acces": [str(a.pk) for a in acces], "action": "suspendre"},
        )
        for inscription in InscriptionModule.objects.all():
            assert inscription.statut == InscriptionModule.StatutAcces.SUSPENDU

    def test_reactivation_groupee(self, client, secretaire, etudiants, module_publie):
        acces = self._acces(etudiants, module_publie)
        InscriptionModule.objects.update(statut=InscriptionModule.StatutAcces.SUSPENDU)
        client.force_login(secretaire)
        client.post(
            reverse("administration:acces_action"),
            {"acces": [str(a.pk) for a in acces], "action": "reactiver"},
        )
        assert InscriptionModule.objects.filter(statut=InscriptionModule.StatutAcces.ACTIF).count() == 3

    def test_revocation_groupee_journalisee(self, client, secretaire, etudiants, module_publie):
        acces = self._acces(etudiants, module_publie)
        client.force_login(secretaire)
        client.post(
            reverse("administration:acces_action"),
            {"acces": [str(a.pk) for a in acces], "action": "revoquer", "motif": "Impayé"},
        )
        assert InscriptionModule.objects.filter(statut=InscriptionModule.StatutAcces.REVOQUE).count() == 3
        assert JournalAudit.objects.filter(action="revocation_acces").count() == 3

    def test_prolongation_groupee(self, client, secretaire, etudiants, module_publie):
        acces = [octroyer(p, module_publie, duree_jours=10, notifier_etudiant=False) for p in etudiants]
        client.force_login(secretaire)
        client.post(
            reverse("administration:acces_action"),
            {"acces": [str(a.pk) for a in acces], "action": "prolonger", "jours": "30"},
        )
        from datetime import timedelta

        from django.utils import timezone

        attendu = timezone.localdate() + timedelta(days=40)
        assert all(i.date_fin_acces == attendu for i in InscriptionModule.objects.all())

    def test_une_prolongation_absurde_est_bornee(self, client, secretaire, etudiants, module_publie):
        acces = self._acces(etudiants, module_publie)
        client.force_login(secretaire)
        client.post(
            reverse("administration:acces_action"),
            {"acces": [str(acces[0].pk)], "action": "prolonger", "jours": "999999"},
        )
        from datetime import timedelta

        from django.utils import timezone

        acces[0].refresh_from_db()
        assert acces[0].date_fin_acces <= timezone.localdate() + timedelta(days=3650)

    def test_sans_selection_rien_ne_change(self, client, secretaire, etudiants, module_publie):
        self._acces(etudiants, module_publie)
        client.force_login(secretaire)
        client.post(reverse("administration:acces_action"), {"action": "suspendre"})
        assert InscriptionModule.objects.filter(statut=InscriptionModule.StatutAcces.ACTIF).count() == 3


@pytest.mark.django_db
class TestOctroiEnMasse:
    def test_ouvre_le_module_a_toute_la_promotion(self, client, secretaire, etudiants, promotion, module_publie):
        client.force_login(secretaire)
        client.post(
            reverse("administration:acces_octroi_masse"),
            {"module": str(module_publie.pk), "promotion": str(promotion.pk), "duree_jours": "365"},
        )
        assert InscriptionModule.objects.filter(module=module_publie).count() == 3

    def test_les_etudiants_suspendus_sont_ecartes(self, client, secretaire, etudiants, promotion, module_publie):
        etudiants[0].statut_inscription = ProfilEtudiant.StatutInscription.SUSPENDU
        etudiants[0].save(update_fields=["statut_inscription"])

        client.force_login(secretaire)
        client.post(
            reverse("administration:acces_octroi_masse"),
            {"module": str(module_publie.pk), "promotion": str(promotion.pk)},
        )
        assert InscriptionModule.objects.filter(module=module_publie).count() == 2

    def test_l_octroi_est_idempotent(self, client, secretaire, etudiants, promotion, module_publie):
        client.force_login(secretaire)
        for _ in range(2):
            client.post(
                reverse("administration:acces_octroi_masse"),
                {"module": str(module_publie.pk), "promotion": str(promotion.pk)},
            )
        assert InscriptionModule.objects.filter(module=module_publie).count() == 3


@pytest.mark.django_db
class TestStatistiquesEtJournal:
    def test_les_statistiques_repondent(self, client, secretaire, etudiants, module_publie):
        octroyer(etudiants[0], module_publie, notifier_etudiant=False)
        client.force_login(secretaire)
        reponse = client.get(reverse("administration:video_statistiques"))
        assert reponse.status_code == 200
        assert reponse.context["total_acces"] == 1
        assert reponse.context["modules_publies"] == 1

    def test_le_journal_repond(self, client, secretaire):
        client.force_login(secretaire)
        assert client.get(reverse("administration:video_journal")).status_code == 200

    def test_un_compte_multi_adresses_est_signale(self, client, secretaire, etudiants, lecon):
        """Le partage d'identifiant se voit dans le nombre d'adresses distinctes."""
        for adresse in ("198.51.100.1", "198.51.100.2", "203.0.113.4", "203.0.113.9"):
            JournalAccesVideo.objects.create(
                utilisateur=etudiants[0].utilisateur,
                lecon=lecon,
                resultat=JournalAccesVideo.Resultat.AUTORISE,
                adresse_ip=adresse,
            )
        client.force_login(secretaire)
        reponse = client.get(reverse("administration:video_journal"))
        assert len(reponse.context["suspects"]) == 1
        assert reponse.context["suspects"][0]["adresses"] == 4

    def test_un_usage_normal_n_est_pas_signale(self, client, secretaire, etudiants, lecon):
        for _ in range(10):
            JournalAccesVideo.objects.create(
                utilisateur=etudiants[0].utilisateur,
                lecon=lecon,
                resultat=JournalAccesVideo.Resultat.AUTORISE,
                adresse_ip="198.51.100.1",
            )
        client.force_login(secretaire)
        assert len(client.get(reverse("administration:video_journal")).context["suspects"]) == 0


@pytest.mark.django_db
class TestExport:
    def test_export_csv(self, client, secretaire, etudiants, module_publie):
        octroyer(etudiants[0], module_publie, notifier_etudiant=False)
        client.force_login(secretaire)
        reponse = client.get(reverse("administration:acces_export"))

        assert reponse.status_code == 200
        assert "text/csv" in reponse["Content-Type"]
        contenu = reponse.content.decode()
        assert "Numéro étudiant" in contenu
        assert module_publie.titre in contenu
        assert JournalAudit.objects.filter(action="export").exists()

    def test_les_formules_de_tableur_sont_neutralisees(self, client, secretaire, etudiants, module_publie):
        """Une cellule commençant par « = » ne doit pas s'exécuter à l'ouverture."""
        etudiants[0].utilisateur.last_name = "=cmd|'/c calc'!A1"
        etudiants[0].utilisateur.save(update_fields=["last_name"])
        octroyer(etudiants[0], module_publie, notifier_etudiant=False)

        client.force_login(secretaire)
        contenu = client.get(reverse("administration:acces_export")).content.decode()
        assert "'=cmd" in contenu
