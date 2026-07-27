"""
Les composants employés par les gabarits doivent exister dans la feuille servie.

Le défaut que ce fichier rend impossible à répéter : `static/css/main.css` est
un artefact de compilation, ignoré par git. Récupérer une branche apporte les
gabarits mais pas les styles. Le site s'ouvre alors avec un HTML neuf sur des
règles anciennes — les rubriques de navigation coulent dans le texte, les
icônes s'affichent à leur taille intrinsèque, et rien, nulle part, ne dit
pourquoi.

Deux filets sont posés ici :

1. **au démarrage** — un contrôle Django nomme le problème et donne la
   commande ; il se déclenche à chaque `runserver` ;
2. **au test** — la vérification ci-dessous échoue sur une feuille périmée,
   avant que quiconque ne rafraîchisse une page cassée.

L'intégration continue construit avant de tester : elle reste verte, et ce
sont les postes de travail que ces contrôles protègent.
"""

from pathlib import Path

import pytest
from django.conf import settings

RACINE = Path(settings.BASE_DIR)
SOURCE = RACINE / "assets" / "css" / "input.css"
CONSTRUITE = RACINE / "static" / "css" / "main.css"

# Composants du système, définis à la main dans « input.css ». Ils ne sont pas
# engendrés par l'analyse des gabarits : une erreur de couche ou une
# construction oubliée les fait disparaître en silence.
COMPOSANTS = [
    "nav-groupe",
    "nav-groupe-panneau",
    "nav-groupe-lien",
    "nav-mobile-groupe",
    "nav-mobile-lien",
    "nav-mobile-panneau",
    "nav-premium",
    "nav-barre",
    "nav-link",
    "nav-cloche",
    "nav-cloche-pastille",
    "nav-avatar",
    "portal-nav-link",
    "portal-nav-pill",
    "portal-nav-group",
    "portal-nav-count",
    "form-input",
    "form-select",
    "form-file",
    "form-checkbox",
    "form-label",
    "form-erreur",
    "form-aide",
    "form-recap-erreurs",
    "champ--invalide",
    "btn-primary",
    "btn-gold",
    "btn-ghost",
    "btn-danger",
    "lien-danger",
    "badge",
    "badge-neutral",
    "card-elevated",
    "table-premium",
    "stat-number",
]

MESSAGE = "\n\nLa feuille servie ne contient pas ce composant.\nLancez : cd src && npm run build"

# Source minimale déclarant un composant, pour les contrôles sur dossier temporaire.
SOURCE_MINIMALE = "@layer components {\n  .nav-groupe {\n    x: y;\n  }\n}"


@pytest.fixture(scope="module")
def feuille() -> str:
    if not CONSTRUITE.exists():
        pytest.fail(f"« {CONSTRUITE} » est absente." + MESSAGE)
    return CONSTRUITE.read_text(encoding="utf-8")


@pytest.mark.parametrize("composant", COMPOSANTS)
def test_le_composant_est_dans_la_feuille_construite(feuille, composant):
    assert f".{composant}" in feuille, f"« .{composant} » introuvable." + MESSAGE


def test_chaque_composant_declare_dans_la_source_est_bien_construit():
    """
    Recensement plutôt qu'énumération : un composant ajouté demain à la source
    est couvert sans que personne n'ait à penser à l'inscrire ci-dessus.

    C'est exactement la situation qui a cassé la barre de navigation : des
    gabarits neufs servis avec des styles anciens.
    """
    from apps.core.checks import composants_manquants

    manquants = composants_manquants()
    assert not manquants, f"Composants déclarés mais absents de la feuille servie : {manquants}{MESSAGE}"


@pytest.mark.django_db
class TestLeControleDeDemarrage:
    """Le filet qui parle au développeur avant même qu'il n'ouvre une page."""

    def test_une_feuille_absente_est_une_erreur(self, tmp_path, settings):
        from apps.core.checks import styles_construits

        (tmp_path / "assets" / "css").mkdir(parents=True)
        (tmp_path / "assets" / "css" / "input.css").write_text("/* source */", encoding="utf-8")
        settings.BASE_DIR = tmp_path

        problemes = styles_construits(None)
        assert [p.id for p in problemes] == ["core.E001"]
        assert "npm run build" in problemes[0].hint

    def test_un_composant_manquant_est_un_avertissement(self, tmp_path, settings):
        """Le cas réel : un composant ajouté à la source, absent des styles servis."""
        from apps.core.checks import styles_construits

        (tmp_path / "assets" / "css").mkdir(parents=True)
        (tmp_path / "static" / "css").mkdir(parents=True)
        (tmp_path / "assets" / "css" / "input.css").write_text(SOURCE_MINIMALE, encoding="utf-8")
        (tmp_path / "static" / "css" / "main.css").write_text(".autre-chose{x:y}", encoding="utf-8")
        settings.BASE_DIR = tmp_path

        problemes = styles_construits(None)
        assert [p.id for p in problemes] == ["core.W001"]
        assert "nav-groupe" in problemes[0].hint
        assert "npm run build" in problemes[0].hint

    def test_une_feuille_a_jour_ne_dit_rien(self, tmp_path, settings):
        from apps.core.checks import styles_construits

        (tmp_path / "assets" / "css").mkdir(parents=True)
        (tmp_path / "static" / "css").mkdir(parents=True)
        (tmp_path / "assets" / "css" / "input.css").write_text(SOURCE_MINIMALE, encoding="utf-8")
        (tmp_path / "static" / "css" / "main.css").write_text(".nav-groupe{x:y}", encoding="utf-8")
        settings.BASE_DIR = tmp_path

        assert styles_construits(None) == []

    def test_une_date_anterieure_ne_suffit_pas_a_alerter(self, tmp_path, settings):
        """
        La comparaison des dates a été essayée et écartée : Tailwind n'écrit sa
        sortie que si le contenu change, si bien qu'une construction à jour
        peut conserver une date antérieure à sa source. Alerter là-dessus
        reviendrait à crier au loup à chaque démarrage.
        """
        import os
        import time

        from apps.core.checks import styles_construits

        (tmp_path / "assets" / "css").mkdir(parents=True)
        (tmp_path / "static" / "css").mkdir(parents=True)
        (tmp_path / "assets" / "css" / "input.css").write_text(SOURCE_MINIMALE, encoding="utf-8")
        construite = tmp_path / "static" / "css" / "main.css"
        construite.write_text(".nav-groupe{x:y}", encoding="utf-8")
        os.utime(construite, (time.time() - 7200, time.time() - 7200))
        settings.BASE_DIR = tmp_path

        assert styles_construits(None) == []
