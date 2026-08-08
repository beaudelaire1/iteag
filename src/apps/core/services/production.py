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

    stripe = {
        "STRIPE_CLE_PUBLIABLE": ("pk_live_", getattr(settings, "STRIPE_CLE_PUBLIABLE", "")),
        "STRIPE_CLE_SECRETE": ("sk_live_", getattr(settings, "STRIPE_CLE_SECRETE", "")),
        "STRIPE_SECRET_WEBHOOK": ("whsec_", getattr(settings, "STRIPE_SECRET_WEBHOOK", "")),
    }
    for nom, (prefixe, valeur) in stripe.items():
        if not valeur:
            anomalies.append(f"{nom} doit être renseigné pour le paiement en ligne.")
        elif not valeur.startswith(prefixe):
            anomalies.append(f"{nom} doit être une valeur de production commençant par « {prefixe} ».")

    if getattr(settings, "ELEARNING_DIFFUSION_VIDEO", "") == "bunny":
        for nom in ("BUNNY_ZONE_DIFFUSION", "BUNNY_CLE_SIGNATURE"):
            if not getattr(settings, nom, ""):
                anomalies.append(f"{nom} doit être renseigné lorsque Bunny est le fournisseur vidéo.")

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
