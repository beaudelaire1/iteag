"""
Libère les suppressions bloquées par les tables des apps retirées.

Les apps « paiements » et « commerce » ont été retirées du code sans migration
pour supprimer leurs tables. Retirer une app d'INSTALLED_APPS et effacer ses
fichiers de migration ne supprime rien en base : Django cesse de connaître ces
tables, mais PostgreSQL continue d'appliquer leurs clés étrangères.

Conséquence observée en production : supprimer un utilisateur, un étudiant, un
module e-learning, une notice de bibliothèque ou une demande d'inscription
échoue sur une ForeignKeyViolation. Django ne peut ni la prévoir ni la cascader,
puisqu'il ignore l'existence des tables qui la déclenchent — l'écran de
confirmation annonce donc un inventaire, puis la suppression casse.

Cette migration retire **uniquement** les sept contraintes qui pointent d'une
table orpheline vers une table vivante. Les tables et leurs lignes sont
conservées : elles portent un historique de commandes et de règlements dont la
valeur comptable doit être tranchée avant toute suppression, et aucune
sauvegarde n'existait au moment où ce défaut a été constaté. Les contraintes
internes aux deux apps retirées sont laissées en place : elles ne bloquent rien.

La migration est sans effet sur une base neuve — celle des tests, où ces tables
n'ont jamais existé — et sur un moteur autre que PostgreSQL.
"""

from django.db import migrations

# (table portant la contrainte, nom de la contrainte, table vivante visée)
CONTRAINTES = [
    (
        "paiements_reglementinscription",
        "paiements_reglementi_demande_id_93129218_fk_academics",
        "academics_demandeinscriptioncours",
    ),
    (
        "paiements_reglement",
        "paiements_reglement_etudiant_id_474b073d_fk_academics",
        "academics_profiletudiant",
    ),
    (
        "paiements_reglement",
        "paiements_reglement_utilisateur_id_a8ad0cc6_fk_accounts_user_id",
        "accounts_user",
    ),
    (
        "paiements_reglement",
        "paiements_reglement_module_id_a20d4307_fk_elearning",
        "elearning_moduleformation",
    ),
    (
        "commerce_commande",
        "commerce_commande_utilisateur_id_f405a6ad_fk_accounts_user_id",
        "accounts_user",
    ),
    (
        "commerce_mouvementstock",
        "commerce_mouvementstock_acteur_id_e0ca051a_fk_accounts_user_id",
        "accounts_user",
    ),
    (
        "commerce_produitlivre",
        "commerce_produitlivr_notice_id_a94c293f_fk_library_n",
        "library_noticebibliographique",
    ),
]


def liberer_les_suppressions(apps, schema_editor):
    """Retire les contraintes, en ignorant les tables absentes.

    Les noms sont des constantes du module, jamais des données saisies : leur
    interpolation dans le SQL ne présente pas de risque d'injection. PostgreSQL
    n'accepte pas de paramètre lié pour un identifiant de table.
    """
    if schema_editor.connection.vendor != "postgresql":
        return

    with schema_editor.connection.cursor() as curseur:
        for table, contrainte, _cible in CONTRAINTES:
            curseur.execute("SELECT to_regclass(%s)", [f"public.{table}"])
            if curseur.fetchone()[0] is None:
                continue  # base neuve : l'app retirée n'a jamais existé ici
            curseur.execute(f'ALTER TABLE "{table}" DROP CONSTRAINT IF EXISTS "{contrainte}"')


def recreer_les_contraintes(apps, schema_editor):
    """
    Volontairement sans effet.

    Une fois les suppressions débloquées, les tables orphelines contiennent des
    références vers des lignes disparues. Recréer les contraintes échouerait sur
    ces références pendantes : la marche arrière n'a pas de sens ici, et prétendre
    l'assurer masquerait le problème au lieu de le signaler.
    """


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0004_alerte_securite"),
    ]

    operations = [
        migrations.RunPython(liberer_les_suppressions, recreer_les_contraintes),
    ]
