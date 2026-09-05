"""
Supprime les tables des apps « paiements » et « commerce ».

Ces deux apps ont été retirées du code sans migration pour effacer leurs tables.
La migration 0005 a levé les sept contraintes qui bloquaient les suppressions
d'utilisateurs, d'étudiants et de notices, mais a délibérément conservé les
tables : leur historique — onze commandes et sept règlements — devait être
tranché avant d'être détruit, et aucune sauvegarde n'existait alors.

Les deux conditions sont désormais remplies. Les sauvegardes PostgreSQL partent
quotidiennement vers R2 et sont vérifiées après envoi ; la décision de ne pas
conserver cet historique a été prise. Les neuf tables partent donc, avec les
entrées « paiements » et « commerce » de l'historique des migrations, qui
prétendaient encore que ces apps étaient appliquées.

Sur les 280 lignes détruites, 205 sont une grille de frais de port et le reste
des mouvements de stock et des alertes de réapprovisionnement : la
configuration d'une boutique qui n'existe plus.

Sans effet sur une base neuve — celle des tests, où ces tables n'ont jamais
existé — et hors PostgreSQL.
"""

from django.db import migrations

# L'ordre n'importe pas : CASCADE emporte les contraintes qui lient ces tables
# entre elles. Aucune ne pointe plus vers une table vivante depuis la 0005.
TABLES = [
    "paiements_evenementstripe",
    "paiements_reglementinscription",
    "paiements_reglement",
    "commerce_alertestock",
    "commerce_lignecommande",
    "commerce_mouvementstock",
    "commerce_produitlivre",
    "commerce_commande",
    "commerce_tariflivraison",
]

APPS_RETIREES = ("paiements", "commerce")


def supprimer_les_tables(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return

    with schema_editor.connection.cursor() as curseur:
        for table in TABLES:
            curseur.execute("SELECT to_regclass(%s)", [f"public.{table}"])
            if curseur.fetchone()[0] is None:
                continue  # base neuve : l'app retirée n'a jamais existé ici
            curseur.execute(f'DROP TABLE IF EXISTS "{table}" CASCADE')

        # Sans cette purge, l'historique continuerait d'affirmer que « commerce »
        # et « paiements » sont appliquées, et un futur « showmigrations »
        # afficherait des apps que plus rien ne définit.
        # « = ANY(%s) » et non « IN %s » : psycopg3 n'adapte pas un tuple Python
        # en liste SQL, il le sérialise en chaîne et la requête ne compile pas.
        curseur.execute("DELETE FROM django_migrations WHERE app = ANY(%s)", [list(APPS_RETIREES)])


def ne_rien_recreer(apps, schema_editor):
    """
    Volontairement sans effet.

    Recréer des tables vides ne restaurerait ni les données ni les modèles qui
    les définissaient — ces derniers ont quitté le dépôt. Une restauration passe
    par la sauvegarde PostgreSQL, pas par une marche arrière de migration qui
    donnerait l'illusion d'avoir rétabli quelque chose.
    """


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0005_liberer_suppressions_apps_retirees"),
    ]

    operations = [
        migrations.RunPython(supprimer_les_tables, ne_rien_recreer),
    ]
