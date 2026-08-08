#!/usr/bin/env sh
# Gate d'exploitation ITEAG à exécuter sur l'hôte Coolify depuis le dossier src.
# Il ne modifie aucune donnée métier. La seule écriture durable potentielle est
# l'envoi des emails de contrôle ; les objets R2 et la base de restauration sont
# créés puis supprimés pendant le test.
#
# Dépendance côté hôte : Docker Compose uniquement. Les requêtes réseau et le
# parsing JSON sont exécutés depuis le conteneur web afin de ne pas supposer la
# présence de curl ou Python sur le serveur.

set -eu

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
GO_LIVE_BASE_URL="${GO_LIVE_BASE_URL:-}"
GO_LIVE_EMAIL_RECIPIENT="${GO_LIVE_EMAIL_RECIPIENT:-}"
GO_LIVE_BUNNY_VIDEO_ID="${GO_LIVE_BUNNY_VIDEO_ID:-}"
GO_LIVE_RESTORE_DB="${GO_LIVE_RESTORE_DB:-iteag_restore_test}"

compose() {
  docker compose -f "$COMPOSE_FILE" "$@"
}

etape() {
  printf '\n\033[1;34m==> %s\033[0m\n' "$1"
}

obligatoire() {
  nom="$1"
  eval "valeur=\${$nom:-}"
  if [ -z "$valeur" ]; then
    echo "ERREUR — variable obligatoire absente : $nom" >&2
    exit 2
  fi
}

obligatoire GO_LIVE_BASE_URL
obligatoire GO_LIVE_EMAIL_RECIPIENT
obligatoire GO_LIVE_BUNNY_VIDEO_ID

etape "Contrat Docker Compose"
compose config --quiet
compose ps

etape "Contrat Django de production"
compose exec -T web python manage.py verifier_production

etape "Healthcheck HTTP public"
compose exec -T web python -c '
import json
import sys
import urllib.request

url = sys.argv[1].rstrip("/") + "/healthz"
request = urllib.request.Request(url, headers={"User-Agent": "ITEAG-go-live/1.0"})
with urllib.request.urlopen(request, timeout=20) as response:
    assert response.status == 200, response.status
    payload = json.load(response)
print(payload)
assert payload.get("statut") == "ok", payload
assert payload.get("base") is True, payload
assert payload.get("cache") is True, payload
' "$GO_LIVE_BASE_URL"

etape "Worker + Beat Celery"
compose exec -T worker celery -A config inspect ping --timeout=5 | grep -q pong
compose exec -T web python manage.py verifier_heartbeat_celery --max-age 180

etape "Sauvegarde PostgreSQL réellement présente sur R2"
compose exec -T backup python3 /opt/iteag/postgres_backup_r2.py status --max-age 129600

etape "Restauration non destructive du dernier dump"
if [ "$GO_LIVE_RESTORE_DB" = "iteag" ]; then
  echo "ERREUR — la base de contrôle ne doit jamais être la base de production." >&2
  exit 2
fi
compose exec -T backup python3 /opt/iteag/postgres_backup_r2.py restore \
  --target-db "$GO_LIVE_RESTORE_DB" \
  --drop-after

etape "Stockage média R2"
compose exec -T web python manage.py verifier_stockage_media

etape "SMTP et gabarits transactionnels"
compose exec -T web python manage.py tester_notifications_email \
  --destinataire "$GO_LIVE_EMAIL_RECIPIENT"

etape "Diffusion Bunny réelle : manifeste + segment"
compose exec -T web python manage.py verifier_bunny "$GO_LIVE_BUNNY_VIDEO_ID"

etape "État final des conteneurs"
compose ps

cat <<'EOF'

OK — les contrôles serveur automatisables sont passés.

Restent volontairement des preuves externes qu'un script local ne peut pas
certifier à lui seul :
- constater la réception des emails de contrôle ;
- constater l'événement de test dans Sentry ;
- valider un Turnstile avec un navigateur humain sur un formulaire public ;
- vérifier la politique de cycle de vie / verrouillage du bucket de sauvegarde ;
- si la carte bancaire est ouverte au lancement : paiement Stripe live réel,
  réception du webhook, rapprochement métier puis remboursement.
EOF
