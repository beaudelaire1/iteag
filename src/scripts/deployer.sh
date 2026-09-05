#!/usr/bin/env sh
# Déploiement ITEAG avec repli automatique sur la révision précédente.
#
# Le problème que ce script résout : jusqu'ici, un déploiement raté laissait le
# site éteint. Trois raisons se cumulaient.
#
#   1. Rien à quoi revenir. Toutes les constructions portaient le même nom
#      d'image ; l'ancienne perdait son nom, puis le nettoyage Docker l'effaçait.
#      La clé « image » de docker-compose.prod.yml corrige cela — ce script en
#      est la contrepartie côté exploitation.
#   2. Les migrations s'exécutaient pendant la bascule. « web » attend que
#      « migrate » ait réussi : une migration en échec, et plus rien ne servait
#      de page. Ici les migrations passent AVANT la bascule, pendant que
#      l'ancienne pile sert toujours. Une migration qui échoue interrompt le
#      déploiement sans jamais toucher au site en service.
#   3. Personne ne vérifiait que la nouvelle pile répondait. Elle est désormais
#      interrogée jusqu'à ce qu'elle serve la bonne révision, et le repli est
#      automatique si elle n'y arrive pas dans le délai imparti.
#
# À exécuter sur l'hôte Coolify, depuis « src ». Dépendances : Docker Compose et
# curl. Le script ne modifie aucune donnée métier ; sa seule écriture est le dump
# de sauvegarde pris avant migration.
#
# Usage :
#   ITEAG_REVISION=<sha> DEPLOY_URL_SANTE=https://iteag.org/healthz ./scripts/deployer.sh

set -eu

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
DEPLOY_URL_SANTE="${DEPLOY_URL_SANTE:-}"
# Trois minutes : au-delà, ce n'est plus un démarrage lent, c'est une panne.
DEPLOY_DELAI="${DEPLOY_DELAI:-180}"
DEPLOY_IMAGES_CONSERVEES="${DEPLOY_IMAGES_CONSERVEES:-5}"
DEPLOY_SAUVEGARDE_AVANT_MIGRATION="${DEPLOY_SAUVEGARDE_AVANT_MIGRATION:-true}"

DEPOT_IMAGE="iteag-app"

compose() {
  docker compose -f "$COMPOSE_FILE" "$@"
}

etape() {
  printf '\n\033[1;34m==> %s\033[0m\n' "$1"
}

avertir() {
  printf '\033[1;33m/!\\ %s\033[0m\n' "$1" >&2
}

erreur() {
  printf '\033[1;31mERREUR — %s\033[0m\n' "$1" >&2
  exit 2
}

obligatoire() {
  eval "valeur=\${$1:-}"
  [ -n "$valeur" ] || erreur "variable obligatoire absente : $1"
}

obligatoire ITEAG_REVISION
obligatoire DEPLOY_URL_SANTE

# ── 1. Vérifier le contrat avant de toucher quoi que ce soit ──────────────────
# Une variable oubliée dans la fiche Coolify fait échouer l'interpolation. Le
# constater ici coûte deux secondes ; le constater après l'arrêt de la pile coûte
# une panne, car la pile ne peut alors même plus redémarrer à l'identique.
etape "Contrat Docker Compose"
compose config --quiet
echo "Le fichier Compose s'interprète et toutes les variables obligatoires sont présentes."

# ── 2. Identifier la version qui sert actuellement ────────────────────────────
etape "Version en service"
conteneur_web="$(compose ps -q web 2>/dev/null || true)"
if [ -n "$conteneur_web" ]; then
  PRECEDENT="$(docker inspect --format '{{.Config.Image}}' "$conteneur_web" | sed 's/.*://')"
else
  PRECEDENT=""
fi

REPLI=""
if [ -z "$PRECEDENT" ]; then
  avertir "aucun conteneur « web » en service : premier déploiement, ou pile arrêtée. Rien à quoi revenir."
elif [ "$PRECEDENT" = "$ITEAG_REVISION" ]; then
  avertir "la révision demandée est déjà celle en service ($PRECEDENT) : redéploiement sans repli distinct."
elif docker image inspect "$DEPOT_IMAGE:$PRECEDENT" >/dev/null 2>&1; then
  REPLI="$PRECEDENT"
  echo "En service : $PRECEDENT — image conservée, le repli est possible."
else
  avertir "la version en service est $PRECEDENT mais son image a disparu du serveur."
  avertir "Le nettoyage automatique d'images de Coolify est probablement actif : le désactiver."
  avertir "CE DÉPLOIEMENT SE FERA SANS FILET."
fi

# ── 3. Construire — l'ancienne pile sert toujours ─────────────────────────────
# Une construction qui échoue s'arrête ici, sans avoir approché les conteneurs
# en service.
etape "Construction de l'image $DEPOT_IMAGE:$ITEAG_REVISION"
compose build

# ── 4. Migrations, avant la bascule ───────────────────────────────────────────
# L'ordre est tout : tant que « web » n'a pas été recréé, un échec de migration
# n'est qu'un déploiement annulé. Après la bascule, c'est une panne.
etape "Schéma de la base"
# La base et le cache sont démarrés s'ils ne le sont pas — sans toucher à « web »,
# « worker » ni « beat », qui continuent de servir l'ancienne version. Sur un
# premier déploiement, c'est aussi ce qui rend la suite exécutable.
compose up -d db redis

migrations_appliquees=0
if compose run --rm --no-deps -T web python manage.py migrate --check >/dev/null 2>&1; then
  echo "Aucune migration en attente."
else
  echo "Migrations en attente."

  # Rien à sauvegarder avant le premier déploiement : la base est vide, et un
  # dump en échec ne doit pas interdire la mise en service initiale.
  if [ "$DEPLOY_SAUVEGARDE_AVANT_MIGRATION" = "true" ] && [ -n "$PRECEDENT" ]; then
    # Le service « backup » attend normalement la fin des migrations : le dump
    # qu'il prend au démarrage est donc postérieur au changement de schéma et ne
    # peut pas servir de point de retour. On en prend un ici, avant, avec
    # « --no-deps » pour ne pas déclencher justement ce qu'on veut précéder.
    etape "Sauvegarde préalable de la base"
    compose run --rm --no-deps -T backup python3 /opt/iteag/postgres_backup_r2.py backup
  elif [ -n "$PRECEDENT" ]; then
    avertir "sauvegarde préalable désactivée : une migration destructrice n'aura pas de point de retour récent."
  fi

  etape "Application des migrations"
  compose run --rm migrate
  migrations_appliquees=1
fi

# ── 5. Bascule ────────────────────────────────────────────────────────────────
etape "Bascule vers $ITEAG_REVISION"
compose up -d --no-build --remove-orphans

# ── 6. Contrôle de santé, et repli s'il n'aboutit pas ─────────────────────────
replier() {
  if [ -z "$REPLI" ]; then
    printf '\033[1;31m%s\033[0m\n' "PANNE — la nouvelle pile ne répond pas et aucune image de repli n'est disponible." >&2
    echo "Journaux : docker compose -f $COMPOSE_FILE logs --tail=200 web" >&2
    exit 1
  fi

  avertir "la nouvelle pile n'a pas répondu dans le délai : repli sur $REPLI."
  ITEAG_REVISION="$REPLI" compose up -d --no-build
  echo "Repli effectué : le site sert de nouveau la révision $REPLI."
  if [ "$migrations_appliquees" = "1" ]; then
    avertir "DES MIGRATIONS ONT ÉTÉ APPLIQUÉES. Revenir à l'image précédente ne les défait pas."
    avertir "Si le schéma n'est pas compatible avec $REPLI, restaurer la sauvegarde prise à l'étape 4."
  fi
  echo "Journaux de la version en échec : docker compose -f $COMPOSE_FILE logs --tail=200 web" >&2
  exit 1
}

etape "Contrôle de santé sur $DEPLOY_URL_SANTE"
debut="$(date +%s)"
while : ; do
  entetes="$(curl -sS -m 10 -D - -o /dev/null "$DEPLOY_URL_SANTE" 2>/dev/null || true)"
  code="$(printf '%s\n' "$entetes" | tr -d '\r' | awk 'NR==1 {print $2}')"
  # La révision servie, et pas seulement un 200 : un ancien conteneur qui aurait
  # survécu à la bascule répondrait 200 sans servir le nouveau code.
  revision="$(printf '%s\n' "$entetes" | tr -d '\r' | awk 'tolower($1) == "x-iteag-revision:" {print $2}')"

  if [ "$code" = "200" ] && [ "$revision" = "$ITEAG_REVISION" ]; then
    echo "La pile répond en 200 et sert bien $ITEAG_REVISION."
    break
  fi

  if [ "$(( $(date +%s) - debut ))" -ge "$DEPLOY_DELAI" ]; then
    avertir "dernier code obtenu : ${code:-aucune réponse}, révision servie : ${revision:-aucune}"
    replier
  fi

  sleep 5
done

# ── 7. Ne garder qu'un nombre borné d'images ──────────────────────────────────
# Un disque plein est une panne comme une autre. La version en service et celle
# de repli ne sont jamais candidates à la suppression, quel que soit leur âge.
etape "Nettoyage des images"
docker image ls "$DEPOT_IMAGE" --format '{{.CreatedAt}}|{{.Tag}}' \
  | sort -r \
  | tail -n "+$(( DEPLOY_IMAGES_CONSERVEES + 1 ))" \
  | cut -d'|' -f2 \
  | while read -r etiquette; do
      if [ "$etiquette" = "$ITEAG_REVISION" ] || [ "$etiquette" = "$PRECEDENT" ]; then
        continue
      fi
      docker image rm "$DEPOT_IMAGE:$etiquette" >/dev/null 2>&1 || true
      echo "Image retirée : $DEPOT_IMAGE:$etiquette"
    done

etape "Déploiement terminé"
echo "Révision en service : $ITEAG_REVISION"
if [ -n "$REPLI" ]; then
  echo "Repli disponible   : $REPLI"
  echo "Pour y revenir     : ITEAG_REVISION=$REPLI docker compose -f $COMPOSE_FILE up -d --no-build"
fi
