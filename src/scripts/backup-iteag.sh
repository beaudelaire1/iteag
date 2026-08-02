#!/usr/bin/env bash
# Sauvegarde quotidienne de la base Postgres du déploiement Coolify.
# Installé sur le VPS : /home/ubuntu/bin/backup-iteag.sh, cron 03h00 (voir docs/exploitation/runbook.md).
set -euo pipefail

DEST=/home/ubuntu/backups
RETENTION_JOURS=30

mkdir -p "$DEST"
DB_CONTAINER=$(docker ps --format '{{.Names}}' | grep '^db-' | head -1)
[ -n "$DB_CONTAINER" ] || { echo "ERREUR : conteneur Postgres introuvable" >&2; exit 1; }

HORODATAGE=$(date +%Y%m%d-%H%M%S)
FICHIER="$DEST/iteag-$HORODATAGE.dump"

# Format custom (-Fc) : compressé, restaurable sélectivement via pg_restore.
docker exec "$DB_CONTAINER" pg_dump -U iteag -d iteag -Fc > "$FICHIER"

# Refuse silencieusement les dumps anormalement petits (base vide, échec partiel).
TAILLE=$(stat -c%s "$FICHIER")
[ "$TAILLE" -gt 10000 ] || { echo "ERREUR : dump suspect ($TAILLE octets)" >&2; exit 1; }

find "$DEST" -name 'iteag-*.dump' -mtime +"$RETENTION_JOURS" -delete

echo "OK $(date -Is) $FICHIER ($(du -h "$FICHIER" | cut -f1))"
