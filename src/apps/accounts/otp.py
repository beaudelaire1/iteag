"""Règles de la double authentification.

Regroupées ici pour que la vue, le middleware et les tests répondent tous à la
même question au même endroit.
"""

from django.conf import settings
from django.db import transaction
from django.utils.crypto import salted_hmac
from django_otp.plugins.otp_static.models import StaticDevice
from django_otp.plugins.otp_totp.models import TOTPDevice

from .models import User

NOM_APPAREIL = "ITEAG"


def deux_facteurs_requis(utilisateur) -> bool:
    """Le second facteur est-il obligatoire pour ce compte ?"""
    if utilisateur is None or not getattr(utilisateur, "is_authenticated", False):
        return False
    if not getattr(settings, "OTP_ENFORCE", True):
        return False
    roles = getattr(settings, "ROLES_2FA_OBLIGATOIRE", [])
    return utilisateur.is_superuser or utilisateur.is_staff or utilisateur.role in roles


def appareils_confirmes(utilisateur):
    """Tous les appareils TOTP confirmés, du plus récent au plus ancien."""
    if utilisateur is None or not getattr(utilisateur, "is_authenticated", False):
        return TOTPDevice.objects.none()
    return TOTPDevice.objects.filter(user=utilisateur, confirmed=True).order_by("-id")


def appareil_confirme(utilisateur) -> TOTPDevice | None:
    """Appareil TOTP confirmé le plus récent, s'il existe."""
    return appareils_confirmes(utilisateur).first()


@transaction.atomic
def appareil_en_attente(utilisateur) -> TOTPDevice:
    """Appareil non confirmé, créé au besoin : le secret survit à un rechargement."""
    # Sérialise les ouvertures de l'écran et la réinitialisation du même compte.
    User.objects.select_for_update().get(pk=utilisateur.pk)
    appareil = TOTPDevice.objects.filter(user=utilisateur, confirmed=False).first()
    if appareil is not None and (
        appareil.last_t >= 0 or appareil.drift != 0 or appareil.t0 != 0 or appareil.last_used_at is not None
    ):
        # Décocher « confirmed » dans l'ancien admin ne réinitialisait ni la
        # clé, ni le compteur anti-rejeu, ni la dérive de l'ancien téléphone.
        TOTPDevice.objects.filter(user=utilisateur, confirmed=False).delete()
        appareil = None
    if appareil is None:
        appareil = TOTPDevice.objects.create(user=utilisateur, name=NOM_APPAREIL, confirmed=False)
    return appareil


def empreinte_appareil(appareil: TOTPDevice) -> str:
    """Lie la saisie aux paramètres du QR affiché, sans stocker sa clé en session."""
    configuration = f"{appareil.key}:{appareil.step}:{appareil.t0}:{appareil.digits}"
    return salted_hmac("accounts.otp.enrolement", configuration).hexdigest()


@transaction.atomic
def reinitialiser_second_facteur(utilisateur) -> tuple[int, int]:
    """Révoque les anciens appareils et la validation OTP de leurs sessions."""
    User.objects.select_for_update().get(pk=utilisateur.pk)
    totp = TOTPDevice.objects.filter(user=utilisateur)
    secours = StaticDevice.objects.filter(user=utilisateur)
    nombre_totp, nombre_secours = totp.count(), secours.count()
    totp.delete()
    secours.delete()
    return nombre_totp, nombre_secours
