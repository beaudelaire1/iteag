# Security Checklist

Utiliser cette checklist pour toute tâche touchant :
- authentification,
- autorisation,
- formulaires,
- données sensibles,
- endpoints,
- configuration,
- intégrations externes,
- uploads,
- traitements côté serveur.

## Contrôles minimum
### Entrées
- Validation stricte des entrées
- Nettoyage adapté au contexte
- Types, formats, bornes, valeurs autorisées
- Rejet explicite des valeurs invalides

### Accès
- Contrôle d’accès explicite
- Vérification des rôles et permissions
- Pas de confiance implicite côté client
- Pas d’accès horizontal ou vertical non contrôlé

### Secrets
- Aucun secret codé en dur
- Usage correct des variables d’environnement
- Pas de fuite dans logs, messages d’erreur ou exemples

### Vulnérabilités classiques
Vérifier selon le contexte :
- injections,
- XSS,
- CSRF,
- SSRF,
- IDOR,
- path traversal,
- exposition d’informations sensibles.

### Logs et erreurs
- Logs utiles mais non sensibles
- Messages d’erreur exploitables sans fuite de détails internes
- Pas de stack trace exposée inutilement

### Dépendances et surface d’attaque
- Pas d’ajout de dépendance sans justification
- Identifier les nouvelles surfaces d’attaque créées par la modification

## Sortie attendue
Quand un risque existe, préciser :
- gravité,
- zone impactée,
- cause probable,
- correction prioritaire,
- validation à faire.