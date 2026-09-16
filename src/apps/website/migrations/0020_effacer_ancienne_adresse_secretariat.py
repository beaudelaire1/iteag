"""Efface de toute la base l'ancienne adresse du secrétariat en @iteag.org.

Le domaine iteag.org ne reçoit aucun courriel : l'institut utilise la boîte
Gmail du secrétariat. L'ancienne adresse pouvait subsister dans des contenus
rédigés (pages, actualités, révisions Wagtail, fiches) et sur l'ancien compte
de démonstration du secrétariat.

- Un compte qui la porte encore perd son adresse, sans en recevoir de
  nouvelle : lui donner la boîte Gmail le ferait passer, à la connexion par
  adresse et au « mot de passe oublié », pour le compte de la secrétaire.
- Partout ailleurs, elle est remplacée par la boîte Gmail, dans toute colonne
  de texte ou JSON. Les journaux (audit, historique Wagtail, tentatives de
  connexion, sessions) ne sont pas réécrits : ils rapportent ce qui a eu lieu.

Chaque table est traitée dans son propre point de sauvegarde : une colonne
récalcitrante est laissée en l'état plutôt que de faire échouer le déploiement.

Cette migration est le seul endroit du dépôt qui nomme encore l'ancienne
adresse — elle doit la connaître pour l'effacer.
"""

from django.db import DatabaseError, migrations, transaction

ANCIENNE = "secretariat@iteag.org"
NOUVELLE = "secretariat.iteag@gmail.com"

TABLES_EXCLUES = {
    "django_migrations",
    "django_session",
    "django_admin_log",
    "core_journalaudit",
    "wagtailcore_modellogentry",
    "wagtailcore_pagelogentry",
    "axes_accessattempt",
    "axes_accessfailurelog",
    "axes_accesslog",
    "elearning_journalaccesvideo",
}
TYPES_TEXTE = {"CharField", "TextField", "EmailField", "SlugField", "URLField"}


def effacer_l_ancienne_adresse(apps, schema_editor):
    connexion = schema_editor.connection
    apps.get_model("accounts", "User").objects.filter(email__iexact=ANCIENNE).update(email="")

    introspection = connexion.introspection
    nom = connexion.ops.quote_name
    motif = f"%{ANCIENNE}%"
    with connexion.cursor() as curseur:
        tables = [t for t in introspection.table_names(curseur) if t not in TABLES_EXCLUES]
        for table in tables:
            for colonne in introspection.get_table_description(curseur, table):
                try:
                    type_champ = introspection.get_field_type(colonne.type_code, colonne)
                except KeyError:
                    continue
                # Seuls les noms de table et de colonne sont interpolés : ils
                # viennent de l'introspection du schéma et passent par
                # quote_name. Les valeurs restent des paramètres.
                t, c = nom(table), nom(colonne.name)
                # SQLite stocke le JSON en texte : seul PostgreSQL (jsonb)
                # demande un passage par ::text.
                json_natif = type_champ == "JSONField" and connexion.vendor == "postgresql"
                if type_champ in TYPES_TEXTE or (type_champ == "JSONField" and not json_natif):
                    requete = f"UPDATE {t} SET {c} = REPLACE({c}, %s, %s) WHERE {c} LIKE %s"  # noqa: S608
                elif json_natif:
                    requete = f"UPDATE {t} SET {c} = REPLACE({c}::text, %s, %s)::jsonb WHERE {c}::text LIKE %s"  # noqa: S608
                else:
                    continue
                try:
                    with transaction.atomic(using=connexion.alias):
                        curseur.execute(requete, [ANCIENNE, NOUVELLE, motif])
                except DatabaseError:
                    continue


class Migration(migrations.Migration):
    dependencies = [
        ("website", "0019_destinataire_contact_secretariat"),
        ("accounts", "0008_invitations_illustrees"),
    ]

    operations = [
        migrations.RunPython(effacer_l_ancienne_adresse, migrations.RunPython.noop),
    ]
