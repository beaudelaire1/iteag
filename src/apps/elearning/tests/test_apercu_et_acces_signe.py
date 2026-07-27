"""
Aperçus gratuits et lecture protégée, du clic à l'adresse délivrée.

Ce fichier tient les deux bouts d'une même règle. L'aperçu doit s'ouvrir à
n'importe qui, sans compte — c'est sa raison d'être commerciale. Tout le reste
ne doit s'ouvrir qu'à un droit vérifié, et l'adresse délivrée doit expirer.

Ce qu'aucun test hors ligne ne peut établir, en revanche : que le CDN accepte
notre jeton. Cela se vérifie contre le compte réel, par
« manage.py verifier_bunny ». Les tests ci-dessous portent sur ce qui est
décidé chez nous — qui obtient une adresse, laquelle, et pour combien de temps.
"""

import json

import pytest
from django.urls import reverse

from apps.academics.models import ProfilEtudiant, Promotion
from apps.accounts.models import User
from apps.elearning.models import (
    Chapitre,
    InscriptionModule,
    JournalAccesVideo,
    Lecon,
    ModuleFormation,
    VideoAsset,
)
from apps.formations.models import Discipline, Parcours, Professeur

ZONE = "https://vz-test.b-cdn.net"


@pytest.fixture(autouse=True)
def _bunny(settings):
    settings.ELEARNING_DIFFUSION_VIDEO = "bunny"
    settings.BUNNY_ZONE_DIFFUSION = ZONE
    settings.BUNNY_CLE_SIGNATURE = "cle-de-test-ne-servant-a-rien"
    settings.BUNNY_LIER_ADRESSE_IP = False


@pytest.fixture
def professeur(db):
    utilisateur = User.objects.create_user(
        username="prof_bunny", email="pb@iteag.org", password="motdepasse-long-12", role=User.Role.ENSEIGNANT
    )
    return Professeur.objects.create(user=utilisateur, nom="Alcide", prenom="Paul", slug="paul-alcide")


@pytest.fixture
def module(db, professeur):
    return ModuleFormation.objects.create(
        titre="Introduction aux Évangiles",
        slug="intro-evangiles",
        discipline=Discipline.objects.create(nom="Nouveau Testament", slug="nt-bunny"),
        responsable=professeur,
        statut=ModuleFormation.StatutPublication.PUBLIE,
        politique_acces=ModuleFormation.PolitiqueAcces.SUR_OCTROI,
    )


def _video(titre, cle, professeur):
    return VideoAsset.objects.create(
        titre=titre,
        cle_stockage=cle,
        fournisseur="bunny",
        uploade_par=professeur.user,
        statut_traitement=VideoAsset.StatutTraitement.PRET,
    )


@pytest.fixture
def lecons(db, module, professeur):
    chapitre = Chapitre.objects.create(module=module, titre="Ouverture", ordre=1)
    apercu = Lecon.objects.create(
        chapitre=chapitre,
        titre="Leçon d'aperçu",
        slug="apercu",
        ordre=1,
        apercu_gratuit=True,
        video=_video("Aperçu", "video-apercu", professeur),
    )
    protegee = Lecon.objects.create(
        chapitre=chapitre,
        titre="Leçon réservée",
        slug="reservee",
        ordre=2,
        video=_video("Réservée", "video-reservee", professeur),
    )
    return {"apercu": apercu, "protegee": protegee}


@pytest.fixture
def etudiant(db):
    parcours = Parcours.objects.create(
        nom="Diplômant", slug="diplomant-bunny", type_parcours=Parcours.TypeParcours.DIPLOMANT_ITEAG
    )
    promotion = Promotion.objects.create(nom="Promo bunny", parcours=parcours, annee_debut=2027, annee_fin=2033)
    utilisateur = User.objects.create_user(
        username="etu_bunny", email="eb@iteag.org", password="motdepasse-long-12", role=User.Role.ETUDIANT
    )
    return ProfilEtudiant.objects.create(
        utilisateur=utilisateur,
        parcours=parcours,
        promotion=promotion,
        numero_etudiant="ETU-BUNNY-1",
        statut_inscription=ProfilEtudiant.StatutInscription.ACTIF,
    )


def demander_lecture(client, module, lecon):
    """Appelle la vue qui délivre une adresse de lecture, comme le fait le lecteur."""
    return client.post(reverse("elearning:lecon_playback", args=[module.slug, lecon.slug]))


# ══════════════════════════════════════════════
# L'aperçu gratuit
# ══════════════════════════════════════════════


@pytest.mark.django_db
class TestApercuGratuit:
    def test_un_visiteur_sans_compte_voit_la_page(self, client, module, lecons):
        reponse = client.get(reverse("elearning:lecon_detail", args=[module.slug, lecons["apercu"].slug]))
        assert reponse.status_code == 200

    def test_un_visiteur_sans_compte_obtient_une_adresse(self, client, module, lecons):
        """C'est la raison d'être de l'aperçu : convaincre avant l'inscription."""
        reponse = demander_lecture(client, module, lecons["apercu"])
        assert reponse.status_code == 200
        donnees = json.loads(reponse.content)
        assert donnees["url"].startswith(ZONE)
        assert donnees["mode"] == "hls"

    def test_l_adresse_d_apercu_est_signee_comme_les_autres(self, client, module, lecons):
        """Gratuit ne veut pas dire ouvert : l'adresse expire aussi."""
        donnees = json.loads(demander_lecture(client, module, lecons["apercu"]).content)
        assert "/bcdn_token=HS256-" in donnees["url"]
        assert "token_path=" in donnees["url"]
        assert donnees["expire_dans"] > 0

    def test_l_apercu_ne_donne_pas_acces_au_reste(self, client, module, lecons):
        """Le point qui compte : un aperçu n'ouvre que lui-même."""
        assert demander_lecture(client, module, lecons["protegee"]).status_code == 403

    def test_la_fiche_du_module_signale_l_apercu(self, client, module, lecons):
        from django.utils.html import escape

        contenu = client.get(module.get_absolute_url()).content.decode()
        # Le titre porte une apostrophe, que Django échappe au rendu.
        assert escape(lecons["apercu"].titre) in contenu

    def test_l_apercu_d_un_module_non_publie_reste_ferme(self, client, module, lecons):
        """Un brouillon n'a pas d'aperçu : rien n'y est encore public."""
        module.statut = ModuleFormation.StatutPublication.BROUILLON
        module.save(update_fields=["statut"])
        assert demander_lecture(client, module, lecons["apercu"]).status_code in (403, 404)


# ══════════════════════════════════════════════
# La lecture protégée
# ══════════════════════════════════════════════


@pytest.mark.django_db
class TestLectureProtegee:
    def test_sans_droit_aucune_adresse_n_est_delivree(self, client, module, lecons, etudiant):
        client.force_login(etudiant.utilisateur)
        assert demander_lecture(client, module, lecons["protegee"]).status_code == 403

    def test_avec_un_droit_actif_l_adresse_est_delivree(self, client, module, lecons, etudiant):
        InscriptionModule.objects.create(etudiant=etudiant, module=module, statut=InscriptionModule.StatutAcces.ACTIF)
        client.force_login(etudiant.utilisateur)
        donnees = json.loads(demander_lecture(client, module, lecons["protegee"]).content)
        assert donnees["url"].startswith(f"{ZONE}/bcdn_token=HS256-")
        assert donnees["url"].endswith("/video-reservee/playlist.m3u8")

    def test_la_revocation_coupe_la_delivrance(self, client, module, lecons, etudiant):
        """
        Le cœur du dispositif : un accès retiré cesse d'ouvrir. L'adresse déjà
        remise reste valable jusqu'à son échéance — c'est pourquoi elle est
        courte.
        """
        acces = InscriptionModule.objects.create(
            etudiant=etudiant, module=module, statut=InscriptionModule.StatutAcces.ACTIF
        )
        client.force_login(etudiant.utilisateur)
        assert demander_lecture(client, module, lecons["protegee"]).status_code == 200

        acces.statut = InscriptionModule.StatutAcces.REVOQUE
        acces.save(update_fields=["statut"])
        assert demander_lecture(client, module, lecons["protegee"]).status_code == 403

    def test_une_demande_en_attente_n_ouvre_rien(self, client, module, lecons, etudiant):
        InscriptionModule.objects.create(etudiant=etudiant, module=module, statut=InscriptionModule.StatutAcces.DEMANDE)
        client.force_login(etudiant.utilisateur)
        assert demander_lecture(client, module, lecons["protegee"]).status_code == 403

    def test_la_cle_de_signature_ne_sort_jamais(self, client, module, lecons, etudiant):
        InscriptionModule.objects.create(etudiant=etudiant, module=module, statut=InscriptionModule.StatutAcces.ACTIF)
        client.force_login(etudiant.utilisateur)
        contenu = demander_lecture(client, module, lecons["protegee"]).content.decode()
        assert "cle-de-test" not in contenu

    def test_aucune_adresse_de_lecture_dans_le_gabarit(self, client, module, lecons, etudiant):
        """
        Règle absolue de l'ADR-005 : la page ne contient jamais l'adresse. Le
        lecteur la demande à part, et le droit est revérifié à ce moment-là.
        """
        InscriptionModule.objects.create(etudiant=etudiant, module=module, statut=InscriptionModule.StatutAcces.ACTIF)
        client.force_login(etudiant.utilisateur)
        contenu = client.get(
            reverse("elearning:lecon_detail", args=[module.slug, lecons["protegee"].slug])
        ).content.decode()
        assert "playlist.m3u8" not in contenu
        assert "token=" not in contenu

    def test_chaque_demande_est_journalisee(self, client, module, lecons, etudiant):
        """Refus comme succès : c'est le journal qui rend le partage détectable."""
        client.force_login(etudiant.utilisateur)
        demander_lecture(client, module, lecons["protegee"])
        entree = JournalAccesVideo.objects.filter(utilisateur=etudiant.utilisateur).first()
        assert entree is not None
        assert entree.resultat != JournalAccesVideo.Resultat.AUTORISE


# ══════════════════════════════════════════════
# L'invariant de protection
# ══════════════════════════════════════════════


@pytest.mark.django_db
class TestUnFournisseurFaibleNeSertPasUnModuleProtege:
    """
    Coller un identifiant YouTube sur une leçon réservée percerait tout le
    contrôle d'accès sans qu'aucune alerte ne se déclenche.
    """

    def test_youtube_est_refuse_sur_un_module_sur_octroi(self, module, professeur, settings):
        from django.core.exceptions import ValidationError

        settings.DEBUG = False
        chapitre = Chapitre.objects.create(module=module, titre="Chapitre", ordre=1)
        video = VideoAsset.objects.create(
            titre="Bande-annonce",
            cle_stockage="dQw4w9WgXcQ",
            fournisseur="youtube",
            uploade_par=professeur.user,
            statut_traitement=VideoAsset.StatutTraitement.PRET,
        )
        lecon = Lecon(chapitre=chapitre, titre="Leçon", slug="lecon-youtube", ordre=1, video=video)
        with pytest.raises(ValidationError):
            lecon.full_clean()

    def test_bunny_est_accepte(self, module, professeur):
        chapitre = Chapitre.objects.create(module=module, titre="Chapitre", ordre=1)
        lecon = Lecon(
            chapitre=chapitre,
            titre="Leçon",
            slug="lecon-bunny",
            ordre=1,
            video=_video("Bunny", "abc", professeur),
        )
        lecon.full_clean()  # ne lève pas


# ══════════════════════════════════════════════
# Un module tout en aperçu ne protège rien
# ══════════════════════════════════════════════


@pytest.mark.django_db
class TestUnModuleNePeutPasEtreEntierementEnApercu:
    """
    L'aperçu court-circuite le contrôle d'accès : c'est voulu, et c'est sans
    danger tant qu'il porte sur une partie du module. Coché sur *toutes* les
    leçons, il rend gratuit un module annoncé comme réservé — sans qu'aucun
    écran ne le dise. C'est ainsi que « test-formation-video » s'est retrouvé
    ouvert à tous, ses trois leçons cochées une à une.
    """

    def test_toutes_les_lecons_en_apercu_bloquent_la_publication(self, module, lecons):
        for lecon in lecons.values():
            lecon.apercu_gratuit = True
            lecon.save(update_fields=["apercu_gratuit"])

        publiable, motif = module.peut_etre_publie()
        assert publiable is False
        assert "aperçu gratuit" in motif

    def test_une_seule_lecon_protegee_suffit(self, module, lecons):
        """La règle interdit le module intégralement gratuit, pas l'aperçu."""
        assert lecons["apercu"].apercu_gratuit is True
        assert lecons["protegee"].apercu_gratuit is False
        publiable, _motif = module.peut_etre_publie()
        assert publiable is True

    def test_un_module_public_peut_tout_offrir(self, module, lecons):
        """Rien à protéger, donc rien à trahir : la règle ne s'y applique pas."""
        module.politique_acces = ModuleFormation.PolitiqueAcces.PUBLIC
        module.save(update_fields=["politique_acces"])
        for lecon in lecons.values():
            lecon.apercu_gratuit = True
            lecon.save(update_fields=["apercu_gratuit"])

        publiable, _motif = module.peut_etre_publie()
        assert publiable is True

    def test_un_module_sans_lecon_n_est_pas_dit_tout_en_apercu(self, module):
        """Le motif de refus doit rester celui qui explique vraiment la situation."""
        assert module.apercus_couvrent_tout() is False
        _publiable, motif = module.peut_etre_publie()
        assert "aucune leçon" in motif


# ══════════════════════════════════════════════
# La politique d'accès, entre les mains du responsable
# ══════════════════════════════════════════════


@pytest.mark.django_db
class TestLeResponsableChoisitLaPolitiqueDAcces:
    def test_le_champ_est_propose(self):
        from apps.elearning.forms import ModuleForm

        assert "politique_acces" in ModuleForm().fields

    def test_un_envoi_sans_politique_ne_relache_rien(self, module):
        """Un champ absent doit retomber sur le plus fermé, jamais sur « public »."""
        from apps.elearning.forms import ModuleForm

        formulaire = ModuleForm(
            instance=module,
            data={
                "titre": module.titre,
                "niveau": ModuleFormation.Niveau.INITIATION,
                "ects": "0",
                "seuil_completion": "80",
            },
        )
        assert formulaire.is_valid() is True
        assert formulaire.cleaned_data["politique_acces"] == ModuleFormation.PolitiqueAcces.SUR_OCTROI

    def test_un_module_neuf_sans_politique_prend_le_defaut_du_modele(self):
        from apps.elearning.forms import ModuleForm

        formulaire = ModuleForm(
            data={
                "titre": "Module neuf",
                "niveau": ModuleFormation.Niveau.INITIATION,
                "ects": "0",
                "seuil_completion": "80",
            }
        )
        assert formulaire.is_valid() is True
        assert formulaire.cleaned_data["politique_acces"] == ModuleFormation.PolitiqueAcces.INSCRIT_PARCOURS

    def test_resserrer_la_politique_est_refuse_si_une_video_ne_suit_pas(self, module, professeur, settings):
        """
        Le modèle vérifie la compatibilité du côté de la leçon. Sans ce
        garde-fou, resserrer la politique après coup laissait des leçons
        servies par un fournisseur incapable de retirer un accès.
        """
        from apps.elearning.forms import ModuleForm

        settings.DEBUG = False
        module.politique_acces = ModuleFormation.PolitiqueAcces.PUBLIC
        module.save(update_fields=["politique_acces"])
        chapitre = Chapitre.objects.create(module=module, titre="Chapitre", ordre=1)
        Lecon.objects.create(
            chapitre=chapitre,
            titre="Bande-annonce",
            slug="bande-annonce",
            ordre=1,
            video=VideoAsset.objects.create(
                titre="Sur YouTube",
                cle_stockage="dQw4w9WgXcQ",
                fournisseur="youtube",
                uploade_par=professeur.user,
                statut_traitement=VideoAsset.StatutTraitement.PRET,
            ),
        )

        formulaire = ModuleForm(
            instance=module,
            data={
                "titre": module.titre,
                "code": "",
                "description": "",
                "objectifs": "",
                "niveau": ModuleFormation.Niveau.INITIATION,
                "ects": "0",
                "politique_acces": ModuleFormation.PolitiqueAcces.SUR_OCTROI,
                "seuil_completion": "80",
            },
        )
        assert formulaire.is_valid() is False
        assert "politique_acces" in formulaire.errors
        assert "Bande-annonce" in formulaire.errors["politique_acces"][0]
