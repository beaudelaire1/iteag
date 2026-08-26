"""Contrat de configuration d'une instance ITEAG prête pour la production.

Ces contrôles ne testent pas la disponibilité réseau des fournisseurs : ils
vérifient que l'application n'est pas ouverte au public avec des valeurs de
repli de développement ou une protection critique désactivée.
"""

from urllib.parse import urlparse

from django.conf import settings


def _origine(url: str) -> str:
    """Retourne schéma + hôte sans chemin, ou une chaîne vide si l'URL est invalide."""
    try:
        parsed = urlparse(url)
    except (TypeError, ValueError):
        return ""
    if not parsed.scheme or not parsed.netloc:
        return ""
    return f"{parsed.scheme}://{parsed.netloc}"


def anomalies_donnees_production() -> list[str]:
    """Écarts qui ne vivent pas dans les réglages, mais dans la base.

    Séparé de `anomalies_configuration_production` à dessein : celui-ci ne lit
    que des réglages et reste utilisable sans base, ce que ses tests exploitent.
    Le contrôle ci-dessous, lui, exige une base prête. La commande
    `verifier_production` exécute les deux.

    Ce que ce contrôle attrape : l'enregistrement « Site » de Wagtail alimente
    la moitié du plan du site et les URL absolues des pages éditoriales. Il vit
    en base, où **aucune variable d'environnement ne le corrige** — corriger
    SITE_URL au moment de la bascule ne le déplace pas. Une préproduction a
    servi des pages dont la balise canonique désignait un hôte qui ne répondait
    plus, et dont le plan du site mêlait deux noms d'hôtes, sans qu'aucun
    contrôle ne s'en aperçoive.
    """
    site_url = getattr(settings, "SITE_URL", "")
    if not _origine(site_url):
        return []
    hote_attendu = urlparse(site_url).hostname or ""

    try:
        from wagtail.models import Site
    except Exception:  # noqa: BLE001 - Wagtail absent : rien à comparer
        return []

    try:
        site = Site.objects.filter(is_default_site=True).only("hostname").first()
    except Exception:  # noqa: BLE001 - base non prête : on le dit, on ne conclut pas
        return ["Le site Wagtail par défaut n'a pas pu être lu : vérifiez son hôte manuellement."]

    if site is None:
        return ["Aucun site Wagtail par défaut n'est défini : les pages éditoriales n'auront pas d'URL absolue."]

    if site.hostname.lower() != hote_attendu.lower():
        return [
            f"Le site Wagtail par défaut est réglé sur « {site.hostname} » "
            f"alors que SITE_URL désigne « {hote_attendu} ». Le plan du site et les URL "
            "des pages éditoriales désigneraient un autre hôte que celui servi au public."
        ]
    return []


def anomalies_configuration_production() -> list[str]:
    """Liste les écarts qui rendent une instance impropre à l'ouverture publique."""
    anomalies: list[str] = []

    if settings.DEBUG:
        anomalies.append("DJANGO_DEBUG doit être False.")

    secret = getattr(settings, "SECRET_KEY", "")
    if len(secret) < 50 or "change-me" in secret.lower():
        anomalies.append("DJANGO_SECRET_KEY doit être un secret de production robuste (50 caractères minimum).")

    site_url = getattr(settings, "SITE_URL", "")
    origine_site = _origine(site_url)
    if not origine_site or not origine_site.startswith("https://"):
        anomalies.append("SITE_URL doit être une URL HTTPS absolue.")

    wagtail_url = getattr(settings, "WAGTAILADMIN_BASE_URL", "")
    if _origine(wagtail_url) != origine_site:
        anomalies.append("WAGTAILADMIN_BASE_URL doit utiliser la même origine HTTPS que SITE_URL.")

    hote = urlparse(site_url).hostname if origine_site else None
    allowed_hosts = set(getattr(settings, "ALLOWED_HOSTS", []))
    if "*" in allowed_hosts:
        anomalies.append("DJANGO_ALLOWED_HOSTS ne doit pas contenir '*'.")
    if hote and hote not in allowed_hosts:
        anomalies.append(f"DJANGO_ALLOWED_HOSTS doit contenir l'hôte public « {hote} ».")

    csrf_origins = set(getattr(settings, "CSRF_TRUSTED_ORIGINS", []))
    if origine_site and origine_site not in csrf_origins:
        anomalies.append("DJANGO_CSRF_TRUSTED_ORIGINS doit contenir l'origine publique de SITE_URL.")

    protections = {
        "SECURE_SSL_REDIRECT": True,
        "SESSION_COOKIE_SECURE": True,
        "CSRF_COOKIE_SECURE": True,
        "SESSION_COOKIE_HTTPONLY": True,
        "CSRF_COOKIE_HTTPONLY": True,
        "SECURE_CONTENT_TYPE_NOSNIFF": True,
        "SECURE_HSTS_INCLUDE_SUBDOMAINS": True,
        "SECURE_HSTS_PRELOAD": True,
    }
    for nom, attendu in protections.items():
        if getattr(settings, nom, None) is not attendu:
            anomalies.append(f"{nom} doit être {attendu} en production.")

    if getattr(settings, "SECURE_HSTS_SECONDS", 0) < 31536000:
        anomalies.append("SECURE_HSTS_SECONDS doit être d'au moins un an.")

    if getattr(settings, "X_FRAME_OPTIONS", "").upper() != "DENY":
        anomalies.append("X_FRAME_OPTIONS doit rester à DENY.")
    if getattr(settings, "SESSION_COOKIE_SAMESITE", None) not in {"Lax", "Strict"}:
        anomalies.append("SESSION_COOKIE_SAMESITE doit être Lax ou Strict.")

    if not getattr(settings, "OTP_ENFORCE", False):
        anomalies.append("DJANGO_OTP_ENFORCE doit être actif.")
    roles_2fa = set(getattr(settings, "ROLES_2FA_OBLIGATOIRE", []))
    if not {"admin", "secretariat"}.issubset(roles_2fa):
        anomalies.append("Le second facteur doit rester obligatoire pour admin et secretariat.")
    if getattr(settings, "AXES_FAILURE_LIMIT", 0) <= 0 or getattr(settings, "AXES_FAILURE_LIMIT", 0) > 5:
        anomalies.append("AXES_FAILURE_LIMIT doit limiter les tentatives de connexion à 5 au maximum.")

    backend_email = getattr(settings, "EMAIL_BACKEND", "")
    if backend_email != "django.core.mail.backends.smtp.EmailBackend":
        anomalies.append("EMAIL_BACKEND doit utiliser SMTP, pas un backend de développement.")
    for nom in ("EMAIL_HOST", "EMAIL_HOST_USER", "EMAIL_HOST_PASSWORD", "DEFAULT_FROM_EMAIL", "SERVER_EMAIL"):
        if not getattr(settings, nom, ""):
            anomalies.append(f"{nom} doit être renseigné.")
    if getattr(settings, "EMAIL_USE_TLS", False) and getattr(settings, "EMAIL_USE_SSL", False):
        anomalies.append("EMAIL_USE_TLS et EMAIL_USE_SSL ne doivent pas être actifs simultanément.")

    if not getattr(settings, "CLOUDFLARE_TURNSTILE_ENABLED", False):
        anomalies.append("Cloudflare Turnstile doit être activé sur les formulaires publics.")
    for nom in ("CLOUDFLARE_TURNSTILE_SITE_KEY", "CLOUDFLARE_TURNSTILE_SECRET_KEY"):
        if not getattr(settings, nom, ""):
            anomalies.append(f"{nom} doit être renseigné.")

    stockage = getattr(settings, "STORAGES", {}).get("default", {}).get("BACKEND", "")
    if "s3" not in stockage.lower():
        anomalies.append("Le stockage média de production doit utiliser le backend S3/R2.")
    for nom in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_STORAGE_BUCKET_NAME", "AWS_S3_ENDPOINT_URL"):
        if not getattr(settings, nom, ""):
            anomalies.append(f"{nom} doit être renseigné pour le stockage média R2.")
    if not getattr(settings, "AWS_QUERYSTRING_AUTH", False):
        anomalies.append("AWS_QUERYSTRING_AUTH doit rester actif pour les médias privés.")

    if not getattr(settings, "SENTRY_DSN", ""):
        anomalies.append("SENTRY_DSN doit être renseigné pour l'observabilité production.")
    if getattr(settings, "SENTRY_SEND_DEFAULT_PII", False):
        anomalies.append("SENTRY_SEND_DEFAULT_PII doit rester False par défaut en production.")

    if getattr(settings, "ELEARNING_DIFFUSION_VIDEO", "") == "bunny":
        for nom in ("BUNNY_ZONE_DIFFUSION", "BUNNY_CLE_SIGNATURE"):
            if not getattr(settings, nom, ""):
                anomalies.append(f"{nom} doit être renseigné lorsque Bunny est le fournisseur vidéo.")
        # Ces deux-là ne sont pas sur le chemin critique — sans elles, la vidéo
        # se lit, mais le lecteur n'affiche aucun chapitre. La dégradation est
        # muette : personne ne signale l'absence d'une fonction qu'il n'a
        # jamais vue. C'est précisément ce qui justifie de la contrôler ici.
        for nom in ("BUNNY_STREAM_LIBRARY_ID", "BUNNY_STREAM_API_KEY"):
            if not getattr(settings, nom, ""):
                anomalies.append(
                    f"{nom} doit être renseigné : sans lui, les chapitres des leçons "
                    "restent vides sans qu'aucune erreur ne le signale."
                )

    # ── Publication légale ──
    #
    # Un site professionnel doit publier l'identité de son éditeur (LCEN
    # art. 6-III) et, dès lors qu'il vend à des consommateurs, désigner un
    # médiateur de la consommation (code de la consommation art. L612-1). Ces
    # pages existent dans le code ; ce qui peut manquer, ce sont les valeurs que
    # seul l'ITEAG connaît. Une mention légale amputée ne vaut pas mieux qu'une
    # mention absente : le manque doit bloquer l'ouverture, pas se découvrir à
    # la lecture.
    mentions = {
        "ITEAG_FORME_JURIDIQUE": "la forme juridique de l'éditeur",
        "ITEAG_IMMATRICULATION": "le numéro d'immatriculation (RNA ou SIREN/SIRET)",
        "ITEAG_DIRECTEUR_PUBLICATION": "le nom du directeur de la publication",
        "ITEAG_HEBERGEUR": "la raison sociale de l'hébergeur",
        "ITEAG_HEBERGEUR_ADRESSE": "l'adresse de l'hébergeur",
    }
    for nom, description in mentions.items():
        if not str(getattr(settings, nom, "") or "").strip():
            anomalies.append(f"{nom} doit être renseigné : les mentions légales doivent publier {description}.")

    database_engine = getattr(settings, "DATABASES", {}).get("default", {}).get("ENGINE", "")
    if database_engine != "django.db.backends.postgresql":
        anomalies.append("La base de production doit utiliser PostgreSQL.")

    cache_backend = getattr(settings, "CACHES", {}).get("default", {}).get("BACKEND", "")
    if "django_redis" not in cache_backend:
        anomalies.append("Le cache de production doit utiliser django-redis.")

    for nom in ("CELERY_BROKER_URL", "CELERY_RESULT_BACKEND"):
        valeur = getattr(settings, nom, "")
        if not valeur.startswith("redis://"):
            anomalies.append(f"{nom} doit utiliser Redis en production.")

    return anomalies
