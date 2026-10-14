"""Publie l'actualité du calendrier 2027 : quatre sessions, huit cours.

Rédigée d'après le calendrier 2027 et le descriptif de la session de Pâques
remis par le secrétariat. La grille des douze soirées de Pâques y devient un
vrai tableau, lisible et accessible, au lieu d'une image.

Même règle que pour les annonces de la rentrée 2026 : la page est créée une
seule fois et jamais réécrite — une actualité déjà présente sous ce slug est
une décision éditoriale humaine. Sans index d'actualités (tests, base neuve),
la migration ne fait rien. Elle travaille avec les vrais modèles, seuls à
connaître « add_child », « save_revision » et « publish ».
"""

import datetime

from django.db import migrations

DATE_PUBLICATION = datetime.date(2026, 10, 13)

SLUG = "calendrier-2027-sessions-iteag"
TITRE = "Calendrier 2027 : les quatre sessions de l'ITEAG"
CHAPEAU = (
    "Quatre sessions rythment l'année 2027 : Carnaval du 8 au 13 février, Pâques en soirée et en "
    "visioconférence du 30 mars au 7 mai, Juillet du 5 au 9 juillet et Toussaint du 25 au 29 "
    "octobre. Huit cours et huit enseignants, de l'épître aux Hébreux aux grands axes de l'éthique "
    "biblique."
)

MATIN_ANTILLES = "8h – 13h"
MATIN_GUYANE = "9h – 14h"
SOIR_ANTILLES = "18h30 – 20h30"
SOIR_GUYANE = "19h30 – 21h30"

SOIREES_PAQUES = (
    "Mardi 30 mars",
    "Vendredi 2 avril",
    "Mardi 6 avril",
    "Vendredi 9 avril",
    "Mardi 13 avril",
    "Vendredi 16 avril",
    "Mardi 20 avril",
    "Vendredi 23 avril",
    "Mardi 27 avril",
    "Vendredi 30 avril",
    "Mardi 4 mai",
    "Vendredi 7 mai",
)


def _cours(*paires):
    """Liste « enseignant — cours », dans l'ordre du calendrier."""
    elements = "".join(f"<li><b>{enseignant}</b> — {cours}</li>" for enseignant, cours in paires)
    return f"<ul>{elements}</ul>"


CONTENU = [
    {
        "type": "chiffres_cles",
        "id": "c2027a01-4e1b-4c5d-9a0e-1f2b3c4d5e01",
        "value": {
            "titre": "L'année 2027 en un coup d'œil",
            "elements": [
                {
                    "valeur": "4 sessions",
                    "libelle": "Carnaval, Pâques, Juillet, Toussaint",
                    "precision": "De février à octobre 2027",
                },
                {
                    "valeur": "8 cours",
                    "libelle": "Huit enseignants",
                    "precision": "Deux cours par session",
                },
                {
                    "valeur": "12 soirées",
                    "libelle": "Session de Pâques",
                    "precision": "En visioconférence, du 30 mars au 7 mai",
                },
                {
                    "valeur": MATIN_ANTILLES,
                    "libelle": "Carnaval, Juillet et Toussaint",
                    "precision": f"{MATIN_GUYANE} en Guyane",
                },
            ],
        },
    },
    {
        "type": "texte",
        "id": "c2027a01-4e1b-4c5d-9a0e-1f2b3c4d5e02",
        "value": (
            "<h2>Le calendrier de l'année</h2>"
            "<p>Chaque session réunit deux cours. Les horaires sont donnés pour la Guadeloupe et la "
            "Martinique, puis pour la Guyane, qui a une heure d'avance : les cours ont lieu au même "
            "moment pour tous.</p>"
        ),
    },
    {
        "type": "tableau",
        "id": "c2027a01-4e1b-4c5d-9a0e-1f2b3c4d5e03",
        "value": {
            "columns": [
                {"type": "texte", "heading": "Session"},
                {"type": "texte", "heading": "Dates"},
                {"type": "texte", "heading": "Guadeloupe et Martinique"},
                {"type": "texte", "heading": "Guyane"},
            ],
            "rows": [
                {
                    "values": [
                        "<p><b>Carnaval</b></p>",
                        "<p>Du lundi 8 au samedi 13 février</p><p><i>Pas de cours le mardi 9</i></p>",
                        f"<p>{MATIN_ANTILLES}</p>",
                        f"<p>{MATIN_GUYANE}</p>",
                    ]
                },
                {
                    "values": [
                        "<p><b>Pâques</b></p>",
                        "<p>Du mardi 30 mars au vendredi 7 mai</p><p><i>12 soirées en visioconférence</i></p>",
                        f"<p>{SOIR_ANTILLES}</p>",
                        f"<p>{SOIR_GUYANE}</p>",
                    ]
                },
                {
                    "values": [
                        "<p><b>Juillet</b></p>",
                        "<p>Du lundi 5 au vendredi 9 juillet</p>",
                        f"<p>{MATIN_ANTILLES}</p>",
                        f"<p>{MATIN_GUYANE}</p>",
                    ]
                },
                {
                    "values": [
                        "<p><b>Toussaint</b></p>",
                        "<p>Du lundi 25 au vendredi 29 octobre</p>",
                        f"<p>{MATIN_ANTILLES}</p>",
                        f"<p>{MATIN_GUYANE}</p>",
                    ]
                },
            ],
            "caption": "",
        },
    },
    {
        "type": "texte",
        "id": "c2027a01-4e1b-4c5d-9a0e-1f2b3c4d5e04",
        "value": (
            "<h2>Carnaval, du 8 au 13 février</h2>"
            "<p>Cinq matinées de cours entre le lundi 8 et le samedi 13 février, de "
            f"{MATIN_ANTILLES} en Guadeloupe et en Martinique ({MATIN_GUYANE} en Guyane). Deux "
            "enseignements consacrés à l'Écriture : une épître du Nouveau Testament et les livres de "
            "sagesse de l'Ancien.</p>"
            + _cours(
                ("Henri Blocher", "Étude de l'épître aux Hébreux"),
                ("Ruth Labeth", "Les livres de sagesse : Proverbes, Ecclésiaste et Job"),
            )
        ),
    },
    {
        "type": "encadre",
        "id": "c2027a01-4e1b-4c5d-9a0e-1f2b3c4d5e05",
        "value": {
            "titre": "Pas de cours le mardi 9 février",
            "contenu": "<p>La session reprend le mercredi 10 février, aux horaires habituels.</p>",
            "tonalite": "important",
        },
    },
    {
        "type": "texte",
        "id": "c2027a01-4e1b-4c5d-9a0e-1f2b3c4d5e06",
        "value": (
            "<h2>Pâques, du 30 mars au 7 mai, en soirée</h2>"
            "<p>À la différence des trois autres, la session de Pâques s'étale sur six semaines, à "
            "raison de deux soirées par semaine, le mardi et le vendredi. Ses deux cours portent sur l'éthique, de la "
            "vie de couple aux grands principes que dégage la Bible.</p>"
            + _cours(
                (
                    "Wilhem Talbot",
                    "Éthique familiale et sexuelle : fidélité, infidélité et accompagnement des couples",
                ),
                ("Alain Nisus", "Les grands axes de l'éthique biblique"),
            )
        ),
    },
    {
        "type": "important",
        "id": "c2027a01-4e1b-4c5d-9a0e-1f2b3c4d5e07",
        "value": {
            "titre": "En visioconférence, sans déplacement",
            "contenu": (
                "<p>La session de Pâques se déroule <b>en soirée, en visioconférence</b> (réunion à "
                f"distance) : de <b>{SOIR_ANTILLES}</b> en Guadeloupe et en Martinique, de "
                f"<b>{SOIR_GUYANE}</b> en Guyane.</p>"
            ),
        },
    },
    {
        "type": "texte",
        "id": "c2027a01-4e1b-4c5d-9a0e-1f2b3c4d5e08",
        "value": "<h3>Les douze soirées de la session de Pâques</h3>",
    },
    {
        "type": "tableau",
        "id": "c2027a01-4e1b-4c5d-9a0e-1f2b3c4d5e09",
        "value": {
            "columns": [
                {"type": "texte", "heading": "Date"},
                {"type": "texte", "heading": "Guadeloupe et Martinique"},
                {"type": "texte", "heading": "Guyane"},
            ],
            "rows": [
                {"values": [f"<p><b>{soiree} 2027</b></p>", f"<p>{SOIR_ANTILLES}</p>", f"<p>{SOIR_GUYANE}</p>"]}
                for soiree in SOIREES_PAQUES
            ],
            "caption": "",
        },
    },
    {
        "type": "texte",
        "id": "c2027a01-4e1b-4c5d-9a0e-1f2b3c4d5e10",
        "value": (
            "<h2>Juillet, du 5 au 9 juillet</h2>"
            f"<p>Cinq matinées, du lundi au vendredi, de {MATIN_ANTILLES} ({MATIN_GUYANE} en Guyane). "
            "La session interroge la manière d'apprendre à l'âge adulte, et ce que signifie être "
            "chrétien aux Antilles et en Guyane.</p>"
            + _cours(
                ("Madely Goram", "Comment apprendre ? Les méthodes d'apprentissage pour adultes"),
                ("Jean Claude Girondin", "Identité antillo-guyanaise, identité chrétienne : comment articuler ?"),
            )
        ),
    },
    {
        "type": "texte",
        "id": "c2027a01-4e1b-4c5d-9a0e-1f2b3c4d5e11",
        "value": (
            "<h2>Toussaint, du 25 au 29 octobre</h2>"
            f"<p>Cinq matinées, du lundi au vendredi, de {MATIN_ANTILLES} ({MATIN_GUYANE} en Guyane), "
            "pour clore l'année : un regard sur d'autres traditions religieuses, et une question "
            "éthique difficile.</p>"
            + _cours(
                ("Karim Arezki", "Étude des religions indiennes et africaines"),
                ("Daniel Reivax", "Les chrétiens et la guerre"),
            )
        ),
    },
    {
        "type": "encadre",
        "id": "c2027a01-4e1b-4c5d-9a0e-1f2b3c4d5e12",
        "value": {
            "titre": "S'inscrire et se renseigner",
            "contenu": (
                "<p>Le secrétariat de l'ITEAG reçoit les inscriptions et répond aux questions. Les "
                "étudiants de l'institut peuvent aussi s'inscrire aux cours depuis leur espace "
                "étudiant.</p>"
                "<ul>"
                "<li>Téléphone : 0690 37 64 17</li>"
                '<li>Courriel : <a href="mailto:secretariat.iteag@gmail.com">'
                "secretariat.iteag@gmail.com</a></li>"
                "</ul>"
            ),
            "tonalite": "conseil",
        },
    },
]


def publier_le_calendrier_2027(apps, schema_editor):
    from apps.website.models import NewsIndexPage, NewsPage
    from apps.website.models_publications import ContenuActualite

    index = NewsIndexPage.objects.first()
    if index is None or NewsPage.objects.filter(slug=SLUG).exists():
        # Pas d'arborescence Wagtail, ou page déjà là : rien à créer.
        return

    actualite = NewsPage(
        title=TITRE,
        slug=SLUG,
        date=DATE_PUBLICATION,
        excerpt=CHAPEAU,
        body=f"<p>{CHAPEAU}</p>",
        meta_description=CHAPEAU[:300],
        search_description=CHAPEAU[:300],
        live=False,
    )
    index.add_child(instance=actualite)
    ContenuActualite.objects.create(actualite=actualite, contenu=CONTENU)
    actualite.save_revision().publish()


class Migration(migrations.Migration):
    dependencies = [
        ("website", "0020_effacer_ancienne_adresse_secretariat"),
    ]

    operations = [
        migrations.RunPython(publier_le_calendrier_2027, migrations.RunPython.noop),
    ]
