"""Service de journalisation d'audit.

Un seul point d'écriture : la trace ne doit jamais être une reconstitution
approximative faite à plusieurs endroits.
"""

from apps.core.models import JournalAudit


def adresse_ip(request):
    """Adresse du client, en tenant compte d'un éventuel proxy de confiance."""
    if request is None:
        return None
    transmise = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if transmise:
        return transmise.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR") or None


def journaliser(
    action: str,
    *,
    utilisateur=None,
    request=None,
    objet=None,
    objet_type: str = "",
    objet_id: str = "",
    objet_libelle: str = "",
    **metadonnees,
) -> JournalAudit:
    """Enregistre une action sensible.

    `objet` renseigne automatiquement type, identifiant et libellé ; les trois
    paramètres explicites permettent de tracer un objet déjà supprimé.
    """
    if utilisateur is None and request is not None:
        candidat = getattr(request, "user", None)
        if candidat is not None and getattr(candidat, "is_authenticated", False):
            utilisateur = candidat

    if objet is not None:
        objet_type = objet_type or objet.__class__.__name__
        objet_id = objet_id or str(getattr(objet, "pk", ""))
        objet_libelle = objet_libelle or str(objet)[:250]

    return JournalAudit.objects.create(
        utilisateur=utilisateur,
        action=action,
        objet_type=objet_type[:100],
        objet_id=objet_id[:64],
        objet_libelle=objet_libelle[:250],
        adresse_ip=adresse_ip(request),
        user_agent=(request.META.get("HTTP_USER_AGENT", "")[:300] if request else ""),
        metadonnees=metadonnees or {},
    )
