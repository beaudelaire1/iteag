import pytest
from django.core.management import CommandError, call_command
from django.test import override_settings

from apps.core.services.production import (
    anomalies_configuration_production,
    anomalies_donnees_production,
)

CONFIGURATION_PRODUCTION = {
    "DEBUG": False,
    "SECRET_KEY": "production-secret-" + "x" * 64,
    "SITE_URL": "https://iteag.org",
    "WAGTAILADMIN_BASE_URL": "https://iteag.org",
    "ALLOWED_HOSTS": ["iteag.org", "www.iteag.org"],
    "CSRF_TRUSTED_ORIGINS": ["https://iteag.org", "https://www.iteag.org"],
    "SECURE_SSL_REDIRECT": True,
    "SESSION_COOKIE_SECURE": True,
    "CSRF_COOKIE_SECURE": True,
    "SESSION_COOKIE_HTTPONLY": True,
    "CSRF_COOKIE_HTTPONLY": True,
    "SESSION_COOKIE_SAMESITE": "Lax",
    "SECURE_CONTENT_TYPE_NOSNIFF": True,
    "SECURE_HSTS_SECONDS": 31536000,
    "SECURE_HSTS_INCLUDE_SUBDOMAINS": True,
    "SECURE_HSTS_PRELOAD": True,
    "X_FRAME_OPTIONS": "DENY",
    "OTP_ENFORCE": True,
    "ROLES_2FA_OBLIGATOIRE": ["admin", "secretariat"],
    "AXES_FAILURE_LIMIT": 5,
    "EMAIL_BACKEND": "django.core.mail.backends.smtp.EmailBackend",
    "EMAIL_HOST": "smtp.example.test",
    "EMAIL_HOST_USER": "iteag",
    "EMAIL_HOST_PASSWORD": "secret",
    "EMAIL_USE_TLS": True,
    "EMAIL_USE_SSL": False,
    "DEFAULT_FROM_EMAIL": "secretariat@iteag.org",
    "SERVER_EMAIL": "errors@iteag.org",
    "CLOUDFLARE_TURNSTILE_ENABLED": True,
    "CLOUDFLARE_TURNSTILE_SITE_KEY": "site-key",
    "CLOUDFLARE_TURNSTILE_SECRET_KEY": "secret-key",
    "STORAGES": {"default": {"BACKEND": "storages.backends.s3boto3.S3Boto3Storage"}},
    "AWS_ACCESS_KEY_ID": "access",
    "AWS_SECRET_ACCESS_KEY": "secret",
    "AWS_STORAGE_BUCKET_NAME": "iteag-media",
    "AWS_S3_ENDPOINT_URL": "https://r2.example.test",
    "AWS_QUERYSTRING_AUTH": True,
    "SENTRY_DSN": "https://public@example.test/1",
    "SENTRY_SEND_DEFAULT_PII": False,
    "STRIPE_CLE_PUBLIABLE": "pk_live_test",
    "STRIPE_CLE_SECRETE": "sk_live_test",
    "STRIPE_SECRET_WEBHOOK": "whsec_test",
    "ELEARNING_DIFFUSION_VIDEO": "bunny",
    "BUNNY_ZONE_DIFFUSION": "https://video.example.test",
    "BUNNY_CLE_SIGNATURE": "video-secret",
    "CACHES": {"default": {"BACKEND": "django_redis.cache.RedisCache"}},
    "CELERY_BROKER_URL": "redis://redis:6379/1",
    "CELERY_RESULT_BACKEND": "redis://redis:6379/2",
    "ITEAG_FORME_JURIDIQUE": "Association déclarée",
    "ITEAG_IMMATRICULATION": "W000000000",
    "ITEAG_DIRECTEUR_PUBLICATION": "La direction de l'ITEAG",
    "ITEAG_HEBERGEUR": "OVH SAS",
    "ITEAG_HEBERGEUR_ADRESSE": "2 rue Kellermann, 59100 Roubaix, France",
    "ITEAG_MEDIATEUR": "Médiateur de la consommation",
}


MENTIONS_LEGALES_OBLIGATOIRES = [
    "ITEAG_FORME_JURIDIQUE",
    "ITEAG_IMMATRICULATION",
    "ITEAG_DIRECTEUR_PUBLICATION",
    "ITEAG_HEBERGEUR",
    "ITEAG_HEBERGEUR_ADRESSE",
    "ITEAG_MEDIATEUR",
]


@pytest.fixture
def moteur_postgresql(settings, monkeypatch):
    """Exerce le garde-fou PostgreSQL sans override_settings(DATABASES).

    Django avertit volontairement quand un test remplace DATABASES. Ici aucune
    connexion n'est ouverte : le contrat ne lit que le nom du backend. Modifier
    l'entrée du dictionnaire en place évite ce faux warning et pytest la restaure
    après le test.
    """
    monkeypatch.setitem(settings.DATABASES["default"], "ENGINE", "django.db.backends.postgresql")


@override_settings(**CONFIGURATION_PRODUCTION)
def test_configuration_complete_est_prete(moteur_postgresql):
    assert anomalies_configuration_production() == []


@override_settings(
    **{
        **CONFIGURATION_PRODUCTION,
        "EMAIL_BACKEND": "django.core.mail.backends.console.EmailBackend",
        "CLOUDFLARE_TURNSTILE_ENABLED": False,
        "SENTRY_DSN": "",
    }
)
def test_les_replis_de_developpement_sont_refuses(moteur_postgresql):
    anomalies = anomalies_configuration_production()

    assert any("EMAIL_BACKEND" in anomalie for anomalie in anomalies)
    assert any("Turnstile" in anomalie for anomalie in anomalies)
    assert any("SENTRY_DSN" in anomalie for anomalie in anomalies)


@override_settings(
    **{
        **CONFIGURATION_PRODUCTION,
        "ALLOWED_HOSTS": ["*"],
        "SITE_URL": "http://iteag.org",
        "WAGTAILADMIN_BASE_URL": "http://iteag.org",
        "CSRF_TRUSTED_ORIGINS": [],
    }
)
def test_une_origine_non_securisee_est_refusee(moteur_postgresql):
    anomalies = anomalies_configuration_production()

    assert any("HTTPS" in anomalie for anomalie in anomalies)
    assert any("'*'" in anomalie for anomalie in anomalies)
    assert any("CSRF_TRUSTED_ORIGINS" in anomalie for anomalie in anomalies)


@override_settings(
    **{
        **CONFIGURATION_PRODUCTION,
        "STRIPE_CLE_PUBLIABLE": "pk_test_123",
        "STRIPE_CLE_SECRETE": "sk_test_123",
    }
)
def test_les_cles_stripe_de_test_sont_refusees(moteur_postgresql):
    anomalies = anomalies_configuration_production()

    assert any("STRIPE_CLE_PUBLIABLE" in anomalie and "pk_live_" in anomalie for anomalie in anomalies)
    assert any("STRIPE_CLE_SECRETE" in anomalie and "sk_live_" in anomalie for anomalie in anomalies)


@override_settings(**CONFIGURATION_PRODUCTION)
def test_la_commande_reussit_sur_une_configuration_complete(capsys, moteur_postgresql):
    call_command("verifier_production", sans_base=True)
    assert "Configuration production : OK" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("nom", "valeur"),
    [
        ("AWS_S3_ENDPOINT_URL", ""),
        ("BUNNY_CLE_SIGNATURE", ""),
        ("EMAIL_HOST_PASSWORD", ""),
        ("STRIPE_SECRET_WEBHOOK", ""),
    ],
)
def test_la_commande_echoue_si_un_secret_fonctionnel_manque(settings, moteur_postgresql, nom, valeur):
    for cle, config in CONFIGURATION_PRODUCTION.items():
        setattr(settings, cle, config)
    setattr(settings, nom, valeur)

    with pytest.raises(CommandError):
        call_command("verifier_production", sans_base=True)


@pytest.mark.parametrize("nom", MENTIONS_LEGALES_OBLIGATOIRES)
def test_une_mention_legale_manquante_refuse_l_ouverture(settings, moteur_postgresql, nom):
    """Publier un site marchand sans identifier son éditeur n'est pas une option.

    Ces valeurs ne sont connues que de l'ITEAG : le contrat de production est le
    seul endroit où leur absence peut être constatée avant l'ouverture publique
    plutôt qu'après.
    """
    for cle, config in CONFIGURATION_PRODUCTION.items():
        setattr(settings, cle, config)
    setattr(settings, nom, "")

    anomalies = anomalies_configuration_production()

    assert any(nom in anomalie for anomalie in anomalies)
    with pytest.raises(CommandError):
        call_command("verifier_production", sans_base=True)


@override_settings(**{**CONFIGURATION_PRODUCTION, "ITEAG_HEBERGEUR": "   "})
def test_une_mention_legale_blanche_vaut_absence(moteur_postgresql):
    """Un espace saisi par erreur dans la console de déploiement reste un manque."""
    assert any("ITEAG_HEBERGEUR" in anomalie for anomalie in anomalies_configuration_production())


@pytest.mark.django_db
class TestLHotePublicEstUnSeulEtMemeHote:
    """L'écart qui a réellement eu lieu : deux hôtes pour une seule instance.

    SITE_URL vient de l'environnement, le « Site » Wagtail vit en base. Corriger
    le premier au moment de la bascule ne déplace pas le second, et rien ne le
    rappelait : la balise canonique et la moitié du plan du site désignaient un
    hôte différent de celui réellement servi.
    """

    @pytest.fixture
    def site_wagtail(self, db):
        from wagtail.models import Site

        return Site.objects.get(is_default_site=True)

    @override_settings(SITE_URL="https://iteag.org")
    def test_un_hote_aligne_ne_signale_rien(self, site_wagtail):
        site_wagtail.hostname = "iteag.org"
        site_wagtail.save(update_fields=["hostname"])

        assert anomalies_donnees_production() == []

    @override_settings(SITE_URL="https://iteag.org")
    def test_la_casse_n_est_pas_un_ecart(self, site_wagtail):
        site_wagtail.hostname = "ITEAG.org"
        site_wagtail.save(update_fields=["hostname"])

        assert anomalies_donnees_production() == []

    @override_settings(SITE_URL="https://iteag.org")
    def test_un_hote_divergent_est_refuse(self, site_wagtail):
        site_wagtail.hostname = "iteag-preprod.137.74.169.188.sslip.io"
        site_wagtail.save(update_fields=["hostname"])

        anomalies = anomalies_donnees_production()

        assert len(anomalies) == 1
        assert "iteag-preprod.137.74.169.188.sslip.io" in anomalies[0]
        assert "iteag.org" in anomalies[0]

    @override_settings(SITE_URL="https://iteag.org")
    def test_l_absence_de_site_par_defaut_est_signalee(self, site_wagtail):
        from wagtail.models import Site

        Site.objects.filter(pk=site_wagtail.pk).update(is_default_site=False)

        assert any("Aucun site Wagtail par défaut" in anomalie for anomalie in anomalies_donnees_production())

    @override_settings(SITE_URL="")
    def test_sans_site_url_le_controle_se_tait(self, site_wagtail):
        """SITE_URL absent est déjà signalé par le contrat de réglages : une cause, un message."""
        assert anomalies_donnees_production() == []

    def test_la_commande_complete_refuse_un_hote_divergent(self, settings, site_wagtail, moteur_postgresql):
        # L'hôte est enregistré **avant** de basculer les réglages : sauvegarder
        # un Site déclenche la purge du cache de Wagtail, et la configuration de
        # production désigne un Redis qui n'existe pas dans les tests.
        site_wagtail.hostname = "autre-hote.example.test"
        site_wagtail.save(update_fields=["hostname"])

        for cle, valeur in CONFIGURATION_PRODUCTION.items():
            if cle == "CACHES":
                continue
            setattr(settings, cle, valeur)

        with pytest.raises(CommandError):
            call_command("verifier_production")
