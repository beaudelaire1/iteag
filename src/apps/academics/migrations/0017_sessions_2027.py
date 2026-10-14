"""Programme les quatre sessions de l'année 2027 et leurs huit cours.

D'après le calendrier 2027 remis par le secrétariat :

- Carnaval, du 8 au 13 février (pas de cours le 9) ;
- Pâques, du 30 mars au 7 mai, en soirée et en visioconférence ;
- Juillet, du 5 au 9 juillet ;
- Toussaint, du 25 au 29 octobre.

Rien de ce qui existe n'est réécrit : une session déjà créée pour la même
période et la même année académique, un cours ou un enseignant déjà présents
sont repris tels quels, puisqu'ils portent les corrections du secrétariat. Un
enseignant absent de la base est créé avec une fiche non publiée : le site ne
montre pas une page vide, la fiche se complète puis se publie depuis l'espace
d'administration.

Sur une base sans disciplines — les tests, une installation neuve — il n'y a
pas de référentiel de formations et la migration ne fait rien.

L'année académique suit la règle du formulaire des sessions : une session qui
commence à partir d'août appartient à l'année qui s'ouvre. La Toussaint 2027
relève donc de 2027-2028.
"""

import datetime

from django.db import migrations
from django.utils.text import slugify

HORAIRE_MATIN = "8h – 13h (Guadeloupe et Martinique) · 9h – 14h (Guyane)"
HORAIRE_SOIR = "18h30 – 20h30 (Guadeloupe et Martinique) · 19h30 – 21h30 (Guyane)"

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
INFOS_PAQUES = "Les douze soirées : " + ", ".join(soiree.lower() for soiree in SOIREES_PAQUES) + " 2027."

DISCIPLINES = {
    "Ancien Testament": 1,
    "Nouveau Testament": 2,
    "Théologie systématique": 3,
    "Histoire de l'Église": 4,
    "Théologie pratique": 5,
}

SESSIONS = [
    {
        "periode": "carnaval",
        "nom": "Session de Carnaval 2027",
        "annee_academique": "2026-2027",
        "date_debut": datetime.date(2027, 2, 8),
        "date_fin": datetime.date(2027, 2, 13),
        "modalite": "hybride",
        "horaires": f"Du lundi 8 au samedi 13 février 2027, sauf le mardi 9 : pas de cours ce jour-là.\n{HORAIRE_MATIN}",
        "informations_pratiques": "",
        "cours": [
            ("Henri", "Blocher", "Étude de l'épître aux Hébreux", "Nouveau Testament"),
            ("Ruth", "Labeth", "Les livres de sagesse (Proverbes, Ecclésiaste, Job)", "Ancien Testament"),
        ],
    },
    {
        "periode": "paques",
        "nom": "Session de Pâques 2027",
        "annee_academique": "2026-2027",
        "date_debut": datetime.date(2027, 3, 30),
        "date_fin": datetime.date(2027, 5, 7),
        "modalite": "distanciel",
        "horaires": f"En soirée, en visioconférence, le mardi et le vendredi.\n{HORAIRE_SOIR}",
        "informations_pratiques": INFOS_PAQUES,
        "cours": [
            (
                "Wilhem",
                "Talbot",
                "Éthique familiale et sexuelle : fidélité, infidélité et accompagnement des couples",
                "Théologie pratique",
            ),
            ("Alain", "Nisus", "Les grands axes de l'éthique biblique", "Théologie pratique"),
        ],
    },
    {
        "periode": "juillet",
        "nom": "Session de Juillet 2027",
        "annee_academique": "2026-2027",
        "date_debut": datetime.date(2027, 7, 5),
        "date_fin": datetime.date(2027, 7, 9),
        "modalite": "hybride",
        "horaires": f"Du lundi 5 au vendredi 9 juillet 2027.\n{HORAIRE_MATIN}",
        "informations_pratiques": "",
        "cours": [
            (
                "Madely",
                "Goram",
                "Comment apprendre ? Les méthodes d'apprentissage pour adultes",
                "Théologie pratique",
            ),
            (
                "Jean Claude",
                "Girondin",
                "Identité antillo-guyanaise, identité chrétienne : comment articuler ?",
                "Théologie pratique",
            ),
        ],
    },
    {
        "periode": "toussaint",
        "nom": "Session de Toussaint 2027",
        "annee_academique": "2027-2028",
        "date_debut": datetime.date(2027, 10, 25),
        "date_fin": datetime.date(2027, 10, 29),
        "modalite": "hybride",
        "horaires": f"Du lundi 25 au vendredi 29 octobre 2027.\n{HORAIRE_MATIN}",
        "informations_pratiques": "",
        "cours": [
            ("Karim", "Arezki", "Étude des religions indiennes et africaines", "Théologie pratique"),
            ("Daniel", "Reivax", "Les chrétiens et la guerre", "Théologie pratique"),
        ],
    },
]


def _slug_libre(modele, base: str) -> str:
    slug, suffixe = base, 2
    while modele.objects.filter(slug=slug).exists():
        slug = f"{base}-{suffixe}"
        suffixe += 1
    return slug


def _discipline(Discipline, nom: str):
    discipline = Discipline.objects.filter(nom__iexact=nom).first()
    if discipline is None:
        discipline = Discipline.objects.filter(slug=slugify(nom)).first()
    if discipline is None:
        discipline = Discipline.objects.create(nom=nom, slug=slugify(nom), ordre=DISCIPLINES.get(nom, 0))
    return discipline


def _professeur(Professeur, prenom: str, nom: str):
    professeur = (
        Professeur.objects.filter(slug=slugify(f"{prenom} {nom}")).first()
        or Professeur.objects.filter(prenom__iexact=prenom, nom__iexact=nom).first()
    )
    if professeur is None:
        professeur = Professeur.objects.create(
            prenom=prenom,
            nom=nom,
            slug=_slug_libre(Professeur, slugify(f"{prenom} {nom}")),
            actif=False,
        )
    return professeur


def _cours(Cours, Discipline, titre: str, discipline: str):
    slug = slugify(titre)[:250]
    cours = Cours.objects.filter(slug=slug).first() or Cours.objects.filter(titre__iexact=titre).first()
    if cours is None:
        cours = Cours.objects.create(titre=titre, slug=slug, discipline=_discipline(Discipline, discipline))
    return cours


def programmer_les_sessions_2027(apps, schema_editor):
    SessionAcademique = apps.get_model("academics", "SessionAcademique")
    CoursDeSession = apps.get_model("academics", "CoursDeSession")
    Cours = apps.get_model("formations", "Cours")
    Discipline = apps.get_model("formations", "Discipline")
    Professeur = apps.get_model("formations", "Professeur")

    if not Discipline.objects.exists():
        # Base sans référentiel de formations : tests ou installation neuve.
        # Y programmer des sessions inventerait des enseignants et des cours
        # que les tests créent eux-mêmes sous les mêmes adresses.
        return

    for programme in SESSIONS:
        session, _ = SessionAcademique.objects.get_or_create(
            periode=programme["periode"],
            annee_academique=programme["annee_academique"],
            defaults={
                "nom": programme["nom"],
                "date_debut": programme["date_debut"],
                "date_fin": programme["date_fin"],
                "statut": "planifiee",
            },
        )
        for prenom, nom, titre, discipline in programme["cours"]:
            cours = _cours(Cours, Discipline, titre, discipline)
            if CoursDeSession.objects.filter(session=session, cours=cours).exists():
                continue
            CoursDeSession.objects.create(
                session=session,
                cours=cours,
                enseignant=_professeur(Professeur, prenom, nom),
                modalite=programme["modalite"],
                horaires=programme["horaires"],
                informations_pratiques=programme["informations_pratiques"],
                statut="programme",
                inscriptions_ouvertes=True,
            )


class Migration(migrations.Migration):
    dependencies = [
        ("academics", "0016_ajouter_paiement_cheque"),
        ("formations", "0004_bibliographie_cours"),
    ]

    operations = [
        migrations.RunPython(programmer_les_sessions_2027, migrations.RunPython.noop),
    ]
