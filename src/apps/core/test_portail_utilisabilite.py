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


def test_le_menu_mobile_ouvert_reste_dans_le_cadre():
    """Ouvert après un défilement, le menu partait au-dessus de l'écran.

    « overflow: hidden » bloque le fond, mais retire à l'en-tête son ancrage :
    un « sticky » sans conteneur qui défile retombe en haut du document, et le
    panneau, qui en est l'enfant, part avec lui. Mesuré au navigateur avant
    correction : panneau à -2124 px, aucun des douze liens atteignable, page
    figée puisque le défilement était bloqué.

    La règle doit vivre dans la couche « components » : posée dans « base »,
    elle était bien présente dans la feuille et n'appliquait rien — une couche
    postérieure l'emporte avant même que les spécificités soient comparées.
    """
    styles = lire(STYLES)

    assert "html.menu-ouvert .nav-premium" in styles, "Rien ne rattache l'en-tête au cadre pendant l'ouverture"
    debut_composants = styles.index("@layer components")
    debut_utilitaires = styles.index("@layer utilities")
    position_regle = styles.index("html.menu-ouvert .nav-premium")
    assert debut_composants < position_regle < debut_utilitaires, (
        "La règle doit être déclarée dans la même couche que « .nav-premium », sinon elle n'a aucun effet"
    )

    regle = styles[position_regle : styles.index("}", position_regle)]
    assert "position: fixed" in regle


def test_le_volet_ne_mene_au_profil_que_par_un_chemin():
    """La carte d'identité en tête du volet doublait l'entrée « Mon profil ».

    Elle n'avait aucune affordance de lien : on l'atteignait par hasard. Chaque
    barre de portail garde son entrée libellée, et la carte redevient ce
    qu'elle montre — qui est connecté.
    """
    socle = lire(TEMPLATES / "partials" / "portal_base.html")
    assert "accounts:profil" not in socle, "La carte d'identité ne doit plus être un lien vers le profil"

    barres = [
        TEMPLATES / "etudiant" / "partials" / "student_nav.html",
        TEMPLATES / "administration" / "partials" / "admin_nav.html",
        TEMPLATES / "administration" / "partials" / "secretariat_nav.html",
        # L'espace enseignant n'a qu'une barre, réutilisée par le présentiel et
        # la vidéo ; « elearning/enseignant/partials/nav.html » ne fait que
        # l'inclure, et rajoutait un second « Mon profil » à la suite.
        TEMPLATES / "lms" / "partials" / "teacher_nav.html",
    ]
    for barre in barres:
        contenu = lire(barre)
        assert contenu.count("accounts:profil") == 1, f"{barre.name} doit mener au profil une fois, et une seule"


def test_l_annonce_des_cours_disponibles_peut_etre_ecartee():
    """Un bandeau qu'on ne peut pas fermer cesse d'être lu, et occupe l'écran.

    Il porte le nombre annoncé : l'écarter mémorise ce nombre, et l'alerte
    revient dès qu'un cours de plus est ouvert. « Ne plus jamais afficher »
    ferait manquer l'annonce suivante.
    """
    tableau = lire(TEMPLATES / "etudiant" / "dashboard.html")
    script = lire(RACINE / "static" / "js" / "iteag.js")

    assert 'data-alerte-effacable="catalogue-etudiant"' in tableau
    assert 'data-alerte-valeur="{{ cours_catalogue_count }}"' in tableau
    assert "data-alerte-fermer" in tableau
    assert 'aria-label="Masquer cette alerte"' in tableau

    assert "initAlertesEffacables" in script
    assert "initAlertesEffacables();" in script, "La fonction doit être appelée au démarrage"
    # Le stockage local peut être refusé : l'alerte doit rester utilisable.
    assert "memoireLocale" in script
