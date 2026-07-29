"""Les actions centrales des portails doivent être visibles sans deviner un onglet."""

from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]
TEMPLATES = RACINE / "templates"
STYLES = RACINE / "assets" / "css" / "input.css"


def lire(chemin):
    return chemin.read_text(encoding="utf-8")


def test_le_volet_lateral_est_visuellement_separe_et_defile_seul():
    gabarit = lire(TEMPLATES / "partials" / "portal_base.html")
    styles = lire(STYLES)

    assert 'class="portal-sidebar hidden lg:block"' in gabarit
    assert 'class="portal-main min-w-0"' in gabarit
    regle = styles[styles.index(".portal-sidebar {") : styles.index("\n    }", styles.index(".portal-sidebar {"))]
    assert "height: calc(100vh - 6.5rem)" in regle
    assert "overflow-y: auto" in regle
    assert "overscroll-behavior: contain" in regle
    assert "border-right:" in regle


def test_le_professeur_voit_creer_un_devoir_depuis_ses_cours():
    liste = lire(TEMPLATES / "lms" / "courses_list.html")
    detail = lire(TEMPLATES / "lms" / "course_detail.html")

    assert "Créer un devoir" in liste
    assert "devoir_create_pour_cours" in liste
    assert "devoir_create_pour_cours" in detail
    assert "Ajoutez une consigne, une période de dépôt et un barème" in detail


def test_l_etudiant_voit_le_depot_avant_les_notes():
    navigation = lire(TEMPLATES / "etudiant" / "partials" / "student_nav.html")
    tableau = lire(TEMPLATES / "etudiant" / "dashboard.html")
    page = lire(TEMPLATES / "etudiant" / "grades.html")

    assert "Devoirs et notes" in navigation
    assert "Déposer le devoir" in tableau
    assert page.index("Travaux à remettre") < page.index("Notes publiées")
    assert "Déposer mon devoir" in page
