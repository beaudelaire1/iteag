"""Règles de la double authentification.

Regroupées ici pour que la vue, le middleware et les tests répondent tous à la
même question au même endroit.
"""

from django.conf import settings
from django_otp.plugins.otp_totp.models import TOTPDevice

NOM_APPAREIL = "ITEAG"


def deux_facteurs_requis(utilisateur) -> bool:
    """Le second facteur est-il obligatoire pour ce compte ?"""
    if utilisateur is None or not getattr(utilisateur, "is_authenticated", False):
        return False
    if not getattr(settings, "OTP_ENFORCE", True):
        return False
    roles = getattr(settings, "ROLES_2FA_OBLIGATOIRE", [])
    return utilisateur.is_superuser or utilisateur.is_staff or utilisateur.role in roles


def appareil_confirme(utilisateur) -> TOTPDevice | None:
    """Appareil TOTP déjà enrôlé, le cas échéant."""
    if utilisateur is None or not getattr(utilisateur, "is_authenticated", False):
        return None
    return TOTPDevice.objects.filter(user=utilisateur, confirmed=True).first()


def appareil_en_attente(utilisateur) -> TOTPDevice:
    """Appareil non confirmé, créé au besoin : le secret survit à un rechargement."""
    appareil = TOTPDevice.objects.filter(user=utilisateur, confirmed=False).first()
    if appareil is None:
        appareil = TOTPDevice.objects.create(user=utilisateur, name=NOM_APPAREIL, confirmed=False)
    return appareil
