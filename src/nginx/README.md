# ⚠️ Ce répertoire ne décrit pas le déploiement de l'ITEAG

**Rien de ce qui est écrit ici n'est servi en production.** L'ITEAG est déployée
par Coolify, qui place son propre Traefik devant le conteneur applicatif et
gère lui-même la terminaison TLS, les certificats, la redirection HTTP → HTTPS
et les en-têtes de proxy. Aucun fichier de ce répertoire n'est monté par
`docker-compose.prod.yml`, ni copié par `Dockerfile.prod` : ils ne sont lus par
personne.

Ces fichiers proviennent d'un scénario de déploiement autonome envisagé avant
le choix de Coolify. Ils sont conservés parce qu'ils resteraient utiles si
l'hébergement changeait — pas parce qu'ils décrivent l'existant.

## Le risque à connaître

Le danger n'est pas qu'ils existent, c'est qu'on les prenne pour la
configuration réelle. Un durcissement écrit ici — un en-tête de sécurité, une
limitation de débit, une règle de cache — **n'aurait aucun effet**, et l'on
croirait la mesure en place.

Les en-têtes de sécurité réellement servis viennent de Django :

| Mesure | Où elle vit réellement |
|---|---|
| CSP, `Permissions-Policy`, `X-Robots-Tag` | `apps/core/middleware.py` et `config/settings/prod.py` |
| HSTS, `X-Frame-Options`, cookies sécurisés | `config/settings/prod.py`, vérifiés par `manage.py verifier_production` |
| Terminaison TLS, certificats, redirection HTTPS | Coolify / Traefik — voir `docs/exploitation/coolify.md` |
| Limitation de débit sur la connexion | `django-axes` (`AXES_FAILURE_LIMIT`) |

Avant de modifier quoi que ce soit ici, vérifier que la mesure visée ne
s'applique pas déjà dans l'une de ces quatre lignes.

## Si l'hébergement change un jour

Ces fichiers seraient un point de départ, pas une configuration prête : ils
n'ont jamais été servis, donc jamais éprouvés. Il faudrait au minimum reprendre
les chemins de certificats, les noms d'hôtes et la cohérence avec les en-têtes
déjà posés par Django, pour ne pas les émettre deux fois.
