#!/usr/bin/env sh
# Gate d'exploitation ITEAG à exécuter sur l'hôte Coolify depuis le dossier src.
# Il ne modifie aucune donnée métier. La seule écriture durable potentielle est
# l'envoi des emails de contrôle ; les objets R2 et la base de restauration sont
# créés puis supprimés pendant le test.
#
# Dépendance côté hôte : Docker Compose uniquement. Les requêtes réseau et le
# parsing JSON sont exécutés depuis le conteneur web afin de ne pas supposer la
# présence de curl, grep ou Python sur le serveur.

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

etape "Hôte public : balise canonique et plan du site"
# Le contrat Django compare SITE_URL au « Site » Wagtail. Il ne peut pas savoir
# sous quel nom d'hôte le proxy sert réellement les pages : c'est ce que vérifie
# la requête ci-dessous, depuis l'extérieur de l'application. Une balise
# canonique qui désigne un autre hôte fait sortir tout le site de l'index.
# Le script est passé au conteneur par l'entrée standard plutôt qu'en « -c » :
# l'analyse de la page demande des apostrophes, qu'une chaîne shell entre
# apostrophes ne peut pas contenir.
compose exec -T web python - "$GO_LIVE_BASE_URL" <<'PYTHON'
import re
import sys
import urllib.request

ENTETES = {"User-Agent": "ITEAG-go-live/1.0"}


def lire(url, delai=20):
    with urllib.request.urlopen(urllib.request.Request(url, headers=ENTETES), timeout=delai) as reponse:
        return reponse.read().decode("utf-8", errors="replace")


base = sys.argv[1].rstrip("/")
html = lire(base + "/")

canonique = re.search(r"""<link[^>]+rel=["']canonical["'][^>]+href=["']([^"']+)""", html)
assert canonique, "Aucune balise canonique sur la page d'accueil."
attendu = base + "/"
obtenu = canonique.group(1)
assert obtenu == attendu, f"Balise canonique {obtenu!r}, attendu {attendu!r}."
print("Balise canonique :", obtenu)

plan = lire(base + "/sitemap.xml", delai=30)
hotes = {re.match(r"https?://([^/]+)", url).group(1) for url in re.findall(r"<loc>([^<]+)</loc>", plan)}
assert hotes, "Plan du site vide."
hote_attendu = re.match(r"https?://([^/]+)", base).group(1)
assert hotes == {hote_attendu}, f"Le plan du site mêle plusieurs hôtes : {sorted(hotes)}."
print("Plan du site : un seul hôte,", hote_attendu)
PYTHON

etape "Pages légales publiées"
compose exec -T web python - "$GO_LIVE_BASE_URL" <<'PYTHON'
import sys
import urllib.request

base = sys.argv[1].rstrip("/")
for chemin in ("/mentions-legales/", "/conditions-generales-de-vente/"):
    requete = urllib.request.Request(base + chemin, headers={"User-Agent": "ITEAG-go-live/1.0"})
    with urllib.request.urlopen(requete, timeout=20) as reponse:
        assert reponse.status == 200, (chemin, reponse.status)
    print("Publiée :", chemin)
PYTHON

etape "Worker + Beat Celery"
compose exec -T worker sh -c 'celery -A config inspect ping --timeout=5 | grep -q pong'
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
- règlement de formation enregistré par virement ou espèces sur place,
  réception du webhook, rapprochement métier puis remboursement.
EOF
