"""
Le verrou des durées de conservation.

Une durée de conservation vit à trois endroits : la tâche qui purge, le
registre des traitements et la politique publiée sur le site. Tant qu'elle
était recopiée dans les trois, elle a divergé — le code appliquait 730 jours
quand la politique en annonçait 365. Ce n'est pas une imprécision interne : une
politique qui annonce une durée que le système n'applique pas est une
information trompeuse au sens de l'article 13 du RGPD, opposable lors d'une
réclamation ou d'un contrôle.

Ce fichier ne juge pas la valeur retenue — c'est une décision du responsable de
traitement. Il vérifie une seule chose, mais il la vérifie des deux côtés : que
ce qui est appliqué et ce qui est publié disent le même nombre. Changer une
durée oblige désormais à toucher aux deux, ou à voir la CI rougir.
"""

import re
from datetime import timedelta
from pathlib import Path

import pytest
from django.conf import settings
from django.utils import timezone

from apps.core.models import JournalAudit
from apps.core.tasks import purger_journal_audit
from apps.elearning.models import JournalAccesVideo
from apps.elearning.tasks import purger_journal_acces
from apps.paiements.models import EvenementStripe
from apps.paiements.tasks import minimiser_charges_utiles

DOCS = Path(__file__).resolve().parents[3] / "docs"
REGISTRE = DOCS / "conformite" / "registre_traitements.md"
POLITIQUE = DOCS / "conformite" / "politique_gestion_donnees.md"
RUNBOOK = DOCS / "exploitation" / "runbook.md"


def _lire(chemin: Path) -> str:
    assert chemin.exists(), f"Document de conformité introuvable : {chemin}"
    return chemin.read_text(encoding="utf-8")


# ══════════════════════════════════════════════
# Ce qui est appliqué est ce qui est publié
# ══════════════════════════════════════════════


class TestLesDocumentsAnnoncentLaDureeAppliquee:
    def test_le_registre_porte_les_trois_durees_arbitrees(self):
        """Le §3 bis est la source documentaire : il doit citer les trois valeurs."""
        registre = _lire(REGISTRE)
        assert f"{settings.RETENTION_JOURNAL_AUDIT_JOURS} jours" in registre
        assert f"**{settings.RETENTION_JOURNAL_ACCES_VIDEO_JOURS} jours**" in registre
        assert f"**{settings.RETENTION_CHARGE_UTILE_STRIPE_JOURS} jours" in registre

    def test_le_journal_d_audit_est_annonce_en_mois_partout(self):
        """
        Les documents parlent en mois, le code en jours. La conversion doit
        tomber juste, sans quoi « 12 mois » publiés couvriraient deux ans.
        """
        mois = round(settings.RETENTION_JOURNAL_AUDIT_JOURS / 365 * 12)
        attendu = f"{mois} mois"

        registre = _lire(REGISTRE)
        assert f"journal d'audit : {attendu}" in registre

        politique = _lire(POLITIQUE)
        assert f"journal de sécurité et d'audit : {attendu}" in politique

        runbook = _lire(RUNBOOK)
        assert f"rétention de {attendu} du journal d'audit" in runbook

    def test_le_runbook_annonce_la_retention_du_journal_d_acces(self):
        runbook = _lire(RUNBOOK)
        attendu = f"rétention de {settings.RETENTION_JOURNAL_ACCES_VIDEO_JOURS} jours du journal d'accès vidéo"
        assert attendu in runbook

    def test_le_runbook_annonce_la_minimisation_stripe(self):
        runbook = _lire(RUNBOOK)
        assert f"plus de {settings.RETENTION_CHARGE_UTILE_STRIPE_JOURS} jours" in runbook

    def test_aucun_document_ne_promet_encore_deux_ans_de_journal(self):
        """
        Le défaut d'origine, nommément : « 2 ans » écrit dans le runbook quand
        la politique annonçait 12 mois. Tant que la durée retenue est
        inférieure, cette formule ne doit plus figurer nulle part.
        """
        if settings.RETENTION_JOURNAL_AUDIT_JOURS >= 730:
            pytest.skip("La durée retenue est bien de deux ans : la formule est légitime.")
        for chemin in (REGISTRE, POLITIQUE, RUNBOOK):
            texte = _lire(chemin)
            for formule in ("rétention de 2 ans du journal", "journal d'audit : 24 mois"):
                assert formule not in texte, f"{chemin.name} annonce encore une rétention périmée."


# ══════════════════════════════════════════════
# Ce qui est publié est ce qui est réellement purgé
# ══════════════════════════════════════════════
#
# Le test ci-dessus compare deux textes. Ceux-ci exercent les tâches : un
# document et un réglage peuvent s'accorder sur une valeur que la tâche
# n'applique pas.


@pytest.mark.django_db
class TestLesTachesAppliquentLaDureeAnnoncee:
    def test_le_journal_d_audit_est_purge_au_seuil_et_pas_avant(self):
        jours = settings.RETENTION_JOURNAL_AUDIT_JOURS
        ancien = JournalAudit.objects.create(action=JournalAudit.Action.CONNEXION, objet_libelle="Trop vieux")
        recent = JournalAudit.objects.create(action=JournalAudit.Action.CONNEXION, objet_libelle="Encore utile")
        JournalAudit.objects.filter(pk=ancien.pk).update(created_at=timezone.now() - timedelta(days=jours + 1))
        JournalAudit.objects.filter(pk=recent.pk).update(created_at=timezone.now() - timedelta(days=jours - 1))

        assert purger_journal_audit() == 1

        assert JournalAudit.objects.filter(pk=ancien.pk).exists() is False
        assert JournalAudit.objects.filter(pk=recent.pk).exists() is True

    def test_le_journal_d_acces_video_est_purge_au_seuil_et_pas_avant(self):
        jours = settings.RETENTION_JOURNAL_ACCES_VIDEO_JOURS
        ancien = JournalAccesVideo.objects.create(
            resultat=JournalAccesVideo.Resultat.AUTORISE,
            adresse_ip="203.0.113.10",
        )
        recent = JournalAccesVideo.objects.create(
            resultat=JournalAccesVideo.Resultat.REFUSE_DROIT,
            adresse_ip="203.0.113.11",
        )
        JournalAccesVideo.objects.filter(pk=ancien.pk).update(created_at=timezone.now() - timedelta(days=jours + 1))
        JournalAccesVideo.objects.filter(pk=recent.pk).update(created_at=timezone.now() - timedelta(days=jours - 1))

        assert purger_journal_acces() == 1

        assert JournalAccesVideo.objects.filter(pk=ancien.pk).exists() is False
        assert JournalAccesVideo.objects.filter(pk=recent.pk).exists() is True

    def test_la_charge_utile_stripe_est_videe_au_seuil_et_pas_avant(self):
        jours = settings.RETENTION_CHARGE_UTILE_STRIPE_JOURS
        charge = {"customer_details": {"email": "payeur@example.org", "name": "Une personne"}}
        ancien = EvenementStripe.objects.create(
            identifiant="evt_ancien",
            type_evenement="checkout.session.completed",
            charge_utile=charge,
            traite=True,
        )
        recent = EvenementStripe.objects.create(
            identifiant="evt_recent",
            type_evenement="checkout.session.completed",
            charge_utile=charge,
            traite=True,
        )
        EvenementStripe.objects.filter(pk=ancien.pk).update(created_at=timezone.now() - timedelta(days=jours + 1))
        EvenementStripe.objects.filter(pk=recent.pk).update(created_at=timezone.now() - timedelta(days=jours - 1))

        assert minimiser_charges_utiles() == 1

        ancien.refresh_from_db()
        recent.refresh_from_db()
        assert ancien.charge_utile == {}
        assert recent.charge_utile == charge

    def test_la_minimisation_preserve_ce_qui_sert_a_la_comptabilite(self):
        """
        Vider la charge utile ne doit rien coûter à l'idempotence ni à la piste
        d'audit : l'identifiant, le type et l'indicateur de traitement restent.
        """
        jours = settings.RETENTION_CHARGE_UTILE_STRIPE_JOURS
        evenement = EvenementStripe.objects.create(
            identifiant="evt_comptable",
            type_evenement="checkout.session.completed",
            charge_utile={"customer_details": {"email": "payeur@example.org"}},
            traite=True,
        )
        EvenementStripe.objects.filter(pk=evenement.pk).update(created_at=timezone.now() - timedelta(days=jours + 1))

        minimiser_charges_utiles()

        evenement.refresh_from_db()
        assert evenement.identifiant == "evt_comptable"
        assert evenement.type_evenement == "checkout.session.completed"
        assert evenement.traite is True
        assert evenement.charge_utile == {}

    def test_un_evenement_non_traite_n_est_jamais_vide(self):
        """
        Sa charge utile est encore ce qui permettrait de le rejouer. La vider
        rendrait irrattrapable exactement le cas que la réparation du webhook
        est censée couvrir.
        """
        jours = settings.RETENTION_CHARGE_UTILE_STRIPE_JOURS
        charge = {"data": {"object": {"client_reference_id": "quelque-chose"}}}
        evenement = EvenementStripe.objects.create(
            identifiant="evt_non_traite",
            type_evenement="checkout.session.completed",
            charge_utile=charge,
            traite=False,
        )
        EvenementStripe.objects.filter(pk=evenement.pk).update(created_at=timezone.now() - timedelta(days=jours + 365))

        assert minimiser_charges_utiles() == 0

        evenement.refresh_from_db()
        assert evenement.charge_utile == charge


# ══════════════════════════════════════════════
# Les purges sont réellement planifiées
# ══════════════════════════════════════════════


class TestLesPurgesSontPlanifiees:
    """Une tâche de purge que Beat n'appelle jamais ne purge rien."""

    @pytest.mark.parametrize(
        "tache",
        [
            "core.purger_journal_audit",
            "elearning.purger_journal_acces",
            "paiements.minimiser_charges_utiles",
            "paiements.reparer_livraisons",
        ],
    )
    def test_la_tache_figure_au_planificateur(self, tache):
        planifiees = {entree["task"] for entree in settings.CELERY_BEAT_SCHEDULE.values()}
        assert tache in planifiees

    def test_le_runbook_documente_chaque_tache_planifiee(self):
        """
        Le §4 du runbook est ce que lit l'exploitant. Une tâche qui tourne sans
        y figurer est une tâche que personne ne surveille.
        """
        runbook = _lire(RUNBOOK)
        for entree in settings.CELERY_BEAT_SCHEDULE.values():
            assert f"`{entree['task']}`" in runbook, (
                f"La tâche planifiée {entree['task']} ne figure pas au §4 du runbook."
            )


@pytest.mark.parametrize(
    ("module", "fonction"),
    [
        ("core", "purger_journal_audit"),
        ("elearning", "purger_journal_acces"),
        ("paiements", "minimiser_charges_utiles"),
    ],
)
def test_aucune_duree_arbitree_n_est_figee_dans_une_signature(module, fonction):
    """
    Le défaut d'origine était un littéral dans la signature de la tâche —
    `purger_journal_audit(jours=730)` — que rien ne reliait au registre. Une
    valeur par défaut réintroduite ici rouvrirait la divergence que ce fichier
    vient fermer : les trois durées du §3 bis doivent venir des réglages.
    """
    source = (Path(__file__).resolve().parents[1] / module / "tasks.py").read_text(encoding="utf-8")
    signature = re.search(rf"def {fonction}\(([^)]*)\)", source)
    assert signature is not None, f"{module}.{fonction} est introuvable."
    assert "jours: int | None = None" in signature.group(1), (
        f"{module}.{fonction} doit lire sa durée dans les réglages, pas la figer dans sa signature."
    )
